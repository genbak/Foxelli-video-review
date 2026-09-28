from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Comment, Video


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture
def video():
    key = f"test-{uuid4()}.mp4"
    with SessionLocal() as db:
        value = Video(
            original_filename="test.mp4",
            storage_key=key,
            mime_type="video/mp4",
            byte_size=10,
            duration_ms=10_000,
            brand_context="NONE",
        )
        db.add(value)
        db.commit()
        db.refresh(value)
        video_id = value.id
    yield value
    with SessionLocal() as db:
        db.execute(delete(Comment).where(Comment.video_id == video_id))
        db.execute(delete(Video).where(Video.id == video_id))
        db.commit()
    (get_settings().upload_dir / "media" / key).unlink(missing_ok=True)


def test_rejects_invalid_and_oversized_uploads(client, monkeypatch):
    invalid = client.post(
        "/api/videos",
        data={"brand_context": "NONE"},
        files={"file": ("broken.mp4", b"not a video", "video/mp4")},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_media"

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 4)
    oversized = client.post(
        "/api/videos",
        data={"brand_context": "NONE"},
        files={"file": ("large.mp4", b"12345", "video/mp4")},
    )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "upload_too_large"


def test_comment_timestamp_boundaries_and_persistence(client, video):
    at_start = client.post(
        f"/api/videos/{video.id}/comments",
        json={"timestamp_ms": 0, "text": "Opening frame"},
    )
    at_end = client.post(
        f"/api/videos/{video.id}/comments",
        json={"timestamp_ms": video.duration_ms, "text": "End frame"},
    )
    outside = client.post(
        f"/api/videos/{video.id}/comments",
        json={"timestamp_ms": video.duration_ms + 1, "text": "Too late"},
    )
    assert at_start.status_code == 201
    assert at_end.status_code == 201
    assert outside.status_code == 422
    assert outside.json()["code"] == "timestamp_out_of_range"

    restored = client.get(f"/api/videos/{video.id}")
    assert restored.status_code == 200
    assert [item["text"] for item in restored.json()["comments"]] == ["Opening frame", "End frame"]


def test_human_can_remove_a_saved_comment(client, video):
    created = client.post(
        f"/api/videos/{video.id}/comments",
        json={"timestamp_ms": 1_000, "text": "Remove this note"},
    ).json()
    with SessionLocal() as db:
        ai_comment = Comment(video_id=video.id, timestamp_ms=2_000, text="AI note", author="AI")
        db.add(ai_comment)
        db.commit()
        ai_comment_id = ai_comment.id
    response = client.delete(f"/api/videos/{video.id}/comments/{created['id']}")
    assert response.status_code == 204
    assert client.delete(f"/api/videos/{video.id}/comments/{ai_comment_id}").status_code == 204
    assert client.get(f"/api/videos/{video.id}").json()["comments"] == []
    assert client.delete(f"/api/videos/{video.id}/comments/{created['id']}").status_code == 404


@pytest.mark.parametrize("text", ["", "   ", "x" * 1001])
def test_rejects_invalid_comment_text(client, video, text):
    response = client.post(
        f"/api/videos/{video.id}/comments",
        json={"timestamp_ms": 100, "text": text},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
