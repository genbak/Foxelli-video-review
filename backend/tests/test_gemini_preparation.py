from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from google.genai import types
from sqlalchemy import delete

import app.main as main_module
from app.config import get_settings
from app.db import SessionLocal
from app.gemini_service import (
    EXPIRED_MESSAGE,
    expire_provider_file_if_needed,
    prepare_video,
    recover_interrupted_preparations,
)
from app.main import app
from app.models import Video


def make_video(*, status="PROCESSING", context="NONE", expires_at=None):
    key = f"test-{uuid4()}.mp4"
    path = get_settings().upload_dir / "media" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test video placeholder")
    with SessionLocal() as db:
        video = Video(
            original_filename="test.mp4",
            storage_key=key,
            mime_type="video/mp4",
            byte_size=22,
            duration_ms=10_000,
            brand_context=context,
            ai_status=status,
            ai_error="retry" if status == "FAILED" else None,
            gemini_file_name="files/old" if status == "READY" else None,
            gemini_file_uri="https://example.invalid/video" if status == "READY" else None,
            gemini_file_expires_at=expires_at,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video.id, key


def remove_video(video_id, key):
    with SessionLocal() as db:
        db.execute(delete(Video).where(Video.id == video_id))
        db.commit()
    (get_settings().upload_dir / "media" / key).unlink(missing_ok=True)


class FakeFiles:
    def __init__(self, final_state=types.FileState.ACTIVE):
        self.final_state = final_state

    def upload(self, **kwargs):
        return SimpleNamespace(
            name="files/prepared",
            uri="https://gemini.invalid/files/prepared",
            state=types.FileState.PROCESSING,
            expiration_time=datetime.now(timezone.utc) + timedelta(hours=48),
        )

    def get(self, **kwargs):
        return SimpleNamespace(
            name="files/prepared",
            uri="https://gemini.invalid/files/prepared",
            state=self.final_state,
            expiration_time=datetime.now(timezone.utc) + timedelta(hours=48),
        )


class FakeClient:
    def __init__(self, final_state=types.FileState.ACTIVE):
        self.files = FakeFiles(final_state)

    def close(self):
        pass


def test_preparation_active_becomes_ready(monkeypatch):
    video_id, key = make_video()
    monkeypatch.setattr("app.gemini_service._client", lambda: FakeClient())
    monkeypatch.setattr("app.gemini_service.time.sleep", lambda _: None)
    try:
        prepare_video(video_id)
        with SessionLocal() as db:
            video = db.get(Video, video_id)
            assert video.ai_status == "READY"
            assert video.ai_error is None
            assert video.gemini_file_name == "files/prepared"
            assert video.gemini_file_uri == "https://gemini.invalid/files/prepared"
    finally:
        remove_video(video_id, key)


def test_provider_failure_and_timeout_become_safe_failures(monkeypatch):
    failed_id, failed_key = make_video()
    timeout_id, timeout_key = make_video()
    monkeypatch.setattr("app.gemini_service.time.sleep", lambda _: None)
    try:
        monkeypatch.setattr(
            "app.gemini_service._client", lambda: FakeClient(types.FileState.FAILED)
        )
        prepare_video(failed_id)
        with SessionLocal() as db:
            failed = db.get(Video, failed_id)
            assert failed.ai_status == "FAILED"
            assert "could not process" in failed.ai_error

        monkeypatch.setattr("app.gemini_service._client", lambda: FakeClient())
        monkeypatch.setattr(get_settings(), "gemini_prepare_timeout_seconds", 0)
        prepare_video(timeout_id)
        with SessionLocal() as db:
            timed_out = db.get(Video, timeout_id)
            assert timed_out.ai_status == "FAILED"
            assert "in time" in timed_out.ai_error
    finally:
        remove_video(failed_id, failed_key)
        remove_video(timeout_id, timeout_key)


def test_recovery_and_expiry_make_preparation_retryable():
    processing_id, processing_key = make_video()
    expired_id, expired_key = make_video(
        status="READY", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    try:
        recover_interrupted_preparations()
        with SessionLocal() as db:
            assert db.get(Video, processing_id).ai_status == "FAILED"
            expired = db.get(Video, expired_id)
            expire_provider_file_if_needed(expired, db)
            assert expired.ai_status == "FAILED"
            assert expired.ai_error == EXPIRED_MESSAGE
            assert expired.gemini_file_uri is None
    finally:
        remove_video(processing_id, processing_key)
        remove_video(expired_id, expired_key)


def test_retry_contract_and_private_provider_fields(monkeypatch):
    video_id, key = make_video(status="FAILED")
    monkeypatch.setattr(main_module, "prepare_video", lambda _: None)
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/videos/{video_id}/prepare")
            assert response.status_code == 202
            body = response.json()
            assert body["ai_status"] == "PROCESSING"
            assert "gemini_file_name" not in body
            assert "gemini_file_uri" not in body

            duplicate = client.post(f"/api/videos/{video_id}/prepare")
            assert duplicate.status_code == 409
            assert duplicate.json()["code"] == "preparation_in_progress"
    finally:
        remove_video(video_id, key)


def test_upload_returns_202_and_schedules_preparation(monkeypatch):
    created = []

    def fake_store(file, context, db):
        video = Video(
            original_filename="upload.mp4",
            storage_key=f"test-{uuid4()}.mp4",
            mime_type="video/mp4",
            byte_size=10,
            duration_ms=1_000,
            brand_context=context,
            ai_status="PROCESSING",
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        created.append(video.id)
        return video

    scheduled = []
    monkeypatch.setattr(main_module, "store_video", fake_store)
    monkeypatch.setattr(main_module, "prepare_video", lambda video_id: scheduled.append(video_id))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/videos",
                data={"brand_context": "NONE"},
                files={"file": ("upload.mp4", b"placeholder", "video/mp4")},
            )
        assert response.status_code == 202
        assert response.json()["ai_status"] == "PROCESSING"
        assert scheduled == created
    finally:
        with SessionLocal() as db:
            db.execute(delete(Video).where(Video.id.in_(created)))
            db.commit()

