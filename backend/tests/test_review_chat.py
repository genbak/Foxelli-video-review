import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

import app.chat_service as chat_service
from app.chat_service import ReviewOutput, build_review_contents, review_video
from app.db import SessionLocal
from app.main import app
from app.models import Comment, Message, Video
from app.prompts import CHAT_SYSTEM_PROMPT, FIRST_PASS_REQUEST, FULL_REVIEW_SYSTEM_PROMPT


def make_ready_video(context="NONE"):
    with SessionLocal() as db:
        video = Video(
            original_filename="review.mp4",
            storage_key=f"test-{uuid4()}.mp4",
            mime_type="video/mp4",
            byte_size=10,
            duration_ms=10_000,
            brand_context=context,
            ai_status="READY",
            gemini_file_name="files/review",
            gemini_file_uri="https://gemini.invalid/files/review",
            gemini_file_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video.id


def remove_video(video_id):
    with SessionLocal() as db:
        db.execute(delete(Video).where(Video.id == video_id))
        db.commit()


class FakeModels:
    def __init__(self, parsed=None, exception=None, capture=None, text=None, finish_reason="STOP"):
        self.parsed = parsed
        self.exception = exception
        self.capture = capture
        self.text = text
        self.finish_reason = finish_reason

    def generate_content(self, **kwargs):
        if self.capture is not None:
            self.capture.update(kwargs)
        if self.exception is not None:
            raise self.exception
        return SimpleNamespace(
            parsed=self.parsed,
            text=self.text,
            candidates=[SimpleNamespace(finish_reason=self.finish_reason)],
            prompt_feedback=None,
            usage_metadata=None,
        )


class FakeClient:
    def __init__(self, parsed=None, exception=None, capture=None, text=None, finish_reason="STOP"):
        self.models = FakeModels(parsed, exception, capture, text, finish_reason)

    def close(self):
        pass


def stored_counts(video_id):
    with SessionLocal() as db:
        return (
            db.scalar(select(func.count()).select_from(Message).where(Message.video_id == video_id)),
            db.scalar(select(func.count()).select_from(Comment).where(Comment.video_id == video_id)),
        )


def test_normal_answer_saves_two_messages_no_comments_and_bounds_history(monkeypatch):
    video_id = make_ready_video()
    capture = {}
    try:
        with SessionLocal() as db:
            db.add(
                Comment(
                    video_id=video_id,
                    timestamp_ms=1_500,
                    text="Keep this existing feedback",
                    author="HUMAN",
                )
            )
            for number in range(22):
                db.add(
                    Message(
                        video_id=video_id,
                        role="USER" if number % 2 == 0 else "ASSISTANT",
                        text=f"history-{number}",
                    )
                )
            db.commit()

        monkeypatch.setattr(
            chat_service,
            "_client",
            lambda _: FakeClient(
                parsed={"message": "The opening explains the product clearly.", "actions": []},
                capture=capture,
            ),
        )
        result = review_video(video_id, "Is the hook working?")
        assert result.user_message.text == "Is the hook working?"
        assert result.assistant_message.role == "ASSISTANT"
        assert result.comments == []

        contents = capture["contents"]
        assert capture["config"].system_instruction == CHAT_SYSTEM_PROMPT
        assert "Earlier assistant answers are conversation history, not verified evidence." in contents[0].parts[-1].text
        context = json.loads(contents[0].parts[-1].text.split("\n", 1)[1])
        assert len(contents[1:-1]) == 20
        assert contents[1].parts[0].text == "history-2"
        assert contents[1].role == "user"
        assert contents[2].role == "model"
        assert context["current_comments"][0]["text"] == "Keep this existing feedback"
        assert context["current_comments"][0]["id"]
        assert contents[-1].parts[0].text == "Is the hook working?"
        video_part = contents[0].parts[0]
        assert video_part.file_data.file_uri == "https://gemini.invalid/files/review"
        assert video_part.video_metadata.fps == 5.0
        assert video_part.media_resolution.level.value == "MEDIA_RESOLUTION_HIGH"
        assert "brand_instruction" not in context
        assert stored_counts(video_id) == (24, 1)
    finally:
        remove_video(video_id)


def test_full_review_uses_final_prompt_and_context(monkeypatch):
    video_id = make_ready_video()
    capture = {}
    monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(
        parsed={"message": "A brief verdict.", "actions": []}, capture=capture,
    ))
    try:
        review_video(video_id, FIRST_PASS_REQUEST)
        assert capture["config"].system_instruction == FULL_REVIEW_SYSTEM_PROMPT
        assert capture["config"].temperature is None
        video_part = capture["contents"][0].parts[0]
        assert video_part.video_metadata.fps == 5.0
        assert video_part.media_resolution.level.value == "MEDIA_RESOLUTION_HIGH"
        assert "Earlier assistant answers" not in capture["contents"][0].parts[-1].text
        assert capture["contents"][-1].parts[0].text == FIRST_PASS_REQUEST
    finally:
        remove_video(video_id)


def test_valid_actions_persist_atomically_and_are_public(monkeypatch):
    video_id = make_ready_video()
    monkeypatch.setattr(
        chat_service,
        "_client",
        lambda _: FakeClient(
            parsed={
                "message": "I added one focused timeline note.",
                "actions": [
                    {
                        "type": "add_comment",
                        "timestamp_seconds": 8.2345,
                        "text": "Show the finished result here.",
                    }
                ],
            }
        ),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/videos/{video_id}/chat",
                json={"message": "Add that as a comment."},
            )
            assert response.status_code == 201
            body = response.json()
            assert body["comments"][0]["timestamp_ms"] == 8235
            assert body["comments"][0]["author"] == "AI"

            restored = client.get(f"/api/videos/{video_id}").json()
            assert [message["role"] for message in restored["messages"]] == [
                "USER",
                "ASSISTANT",
            ]
            assert restored["comments"][0]["author"] == "AI"
            assert "gemini_file_uri" not in restored
    finally:
        remove_video(video_id)


def test_ai_can_edit_and_remove_its_own_comments_when_asked(monkeypatch):
    video_id = make_ready_video()
    try:
        with SessionLocal() as db:
            revised = Comment(video_id=video_id, timestamp_ms=1_000, text="Old AI note", author="AI")
            removed = Comment(video_id=video_id, timestamp_ms=2_000, text="Wrong AI note", author="AI")
            human = Comment(video_id=video_id, timestamp_ms=3_000, text="Human note", author="HUMAN")
            db.add_all([revised, removed, human])
            db.commit()
            revised_id, removed_id, human_id = revised.id, removed.id, human.id

        monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(parsed={
            "message": "I corrected one AI note and removed the other.",
            "actions": [
                {"type": "edit_comment", "comment_id": str(revised_id), "timestamp_seconds": 1.5, "text": "Corrected AI note"},
                {"type": "delete_comment", "comment_id": str(removed_id)},
            ],
        }))
        result = review_video(video_id, "Change the first AI note and remove the second one.")
        assert result.comments == []
        assert [(comment.id, comment.timestamp_ms, comment.text) for comment in result.updated_comments] == [
            (revised_id, 1_500, "Corrected AI note")
        ]
        assert result.deleted_comment_ids == [removed_id]
        with SessionLocal() as db:
            assert db.get(Comment, removed_id) is None
            assert db.get(Comment, human_id).text == "Human note"
        assert stored_counts(video_id) == (2, 2)
    finally:
        remove_video(video_id)


def test_ai_cannot_change_human_comment_and_batch_rolls_back(monkeypatch):
    video_id = make_ready_video()
    try:
        with SessionLocal() as db:
            ai = Comment(video_id=video_id, timestamp_ms=1_000, text="AI note", author="AI")
            human = Comment(video_id=video_id, timestamp_ms=2_000, text="Human note", author="HUMAN")
            db.add_all([ai, human])
            db.commit()
            ai_id, human_id = ai.id, human.id

        monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(parsed={
            "message": "Changed both notes.",
            "actions": [
                {"type": "edit_comment", "comment_id": str(ai_id), "text": "New AI note"},
                {"type": "delete_comment", "comment_id": str(human_id)},
            ],
        }))
        with TestClient(app) as client:
            response = client.post(f"/api/videos/{video_id}/chat", json={"message": "Change both notes"})
        assert response.status_code == 502
        assert response.json()["code"] == "invalid_ai_response"
        with SessionLocal() as db:
            assert db.get(Comment, ai_id).text == "AI note"
            assert db.get(Comment, human_id).text == "Human note"
        assert stored_counts(video_id) == (0, 2)
    finally:
        remove_video(video_id)


@pytest.mark.parametrize(
    "parsed",
    [
        {
            "message": "Bad time",
            "actions": [
                {"type": "add_comment", "timestamp_seconds": 10.001, "text": "Too late"}
            ],
        },
        {
            "message": "Bad number",
            "actions": [
                {"type": "add_comment", "timestamp_seconds": float("nan"), "text": "No"}
            ],
        },
        {
            "message": "Bad action",
            "actions": [{"type": "delete_comment", "timestamp_seconds": 1, "text": "No"}],
        },
        {
            "message": "Too many",
            "actions": [
                {"type": "add_comment", "timestamp_seconds": number, "text": "Note"}
                for number in range(11)
            ],
        },
        {
            "message": "Long text",
            "actions": [
                {"type": "add_comment", "timestamp_seconds": 1, "text": "x" * 1001}
            ],
        },
        {
            "message": "Unexpected field",
            "actions": [],
            "secret_extra": "not part of the contract",
        },
    ],
)
def test_invalid_action_batch_saves_nothing(monkeypatch, parsed):
    video_id = make_ready_video()
    monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(parsed=parsed))
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/videos/{video_id}/chat", json={"message": "Post these comments"}
            )
            assert response.status_code == 502
            assert response.json()["code"] == "invalid_ai_response"
        assert stored_counts(video_id) == (0, 0)
    finally:
        remove_video(video_id)


def test_complete_json_fallback_and_truncated_output(monkeypatch):
    video_id = make_ready_video()
    try:
        monkeypatch.setattr(
            chat_service,
            "_client",
            lambda _: FakeClient(text='{"message":"A clear answer","actions":[]}'),
        )
        result = review_video(video_id, "What do you see?")
        assert result.assistant_message.text == "A clear answer"
        assert stored_counts(video_id) == (2, 0)

        monkeypatch.setattr(
            chat_service,
            "_client",
            lambda _: FakeClient(
                parsed={"message": "Partial result", "actions": []},
                finish_reason="MAX_TOKENS",
            ),
        )
        with TestClient(app) as client:
            response = client.post(
                f"/api/videos/{video_id}/chat", json={"message": "Review again"}
            )
        assert response.status_code == 502
        assert response.json()["code"] == "ai_response_incomplete"
        assert stored_counts(video_id) == (2, 0)
    finally:
        remove_video(video_id)


@pytest.mark.parametrize(
    ("finish_reason", "text", "expected_code"),
    [
        (None, '{"message":"Answer","actions":[]}', "invalid_ai_response"),
        ("SAFETY", '{"message":"Answer","actions":[]}', "invalid_ai_response"),
        ("STOP", "", "invalid_ai_response"),
        ("STOP", '{"message":"Answer","actions":[{"type":"add_comment","timestamp_seconds":1,"text":"Note","extra":1}]}', "invalid_ai_response"),
    ],
)
def test_abnormal_or_invalid_visible_output_saves_nothing(monkeypatch, finish_reason, text, expected_code):
    video_id = make_ready_video()
    monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(text=text, finish_reason=finish_reason))
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/videos/{video_id}/chat", json={"message": "Review"})
        assert response.status_code == 502
        assert response.json()["code"] == expected_code
        assert stored_counts(video_id) == (0, 0)
    finally:
        remove_video(video_id)


def test_ten_actions_is_a_safety_ceiling_not_a_three_comment_quota(monkeypatch):
    video_id = make_ready_video()
    monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(parsed={
        "message": "Ten distinct issues were requested.",
        "actions": [
            {"type": "add_comment", "timestamp_seconds": index, "text": f"Issue {index}"}
            for index in range(10)
        ],
    }))
    try:
        result = review_video(video_id, "Post the ten confirmed issues")
        assert len(result.comments) == 10
        assert stored_counts(video_id) == (2, 10)
    finally:
        remove_video(video_id)


def test_persistence_failure_rolls_back_messages_and_comments(monkeypatch):
    video_id = make_ready_video()
    monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(parsed={
        "message": "A valid answer",
        "actions": [{"type": "add_comment", "timestamp_seconds": 2, "text": "A valid note"}],
    }))
    original_factory = chat_service.SessionLocal
    opened = 0

    def failing_second_session():
        nonlocal opened
        opened += 1
        session = original_factory()
        if opened == 2:
            session.commit = lambda: (_ for _ in ()).throw(RuntimeError("simulated commit failure"))
        return session

    monkeypatch.setattr(chat_service, "SessionLocal", failing_second_session)
    try:
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            review_video(video_id, "Post a comment")
        assert stored_counts(video_id) == (0, 0)
    finally:
        remove_video(video_id)


def test_diagnostics_do_not_log_provider_text(monkeypatch, caplog):
    video_id = make_ready_video()
    private_marker = "PRIVATE_PROVIDER_PAYLOAD_DO_NOT_LOG"
    monkeypatch.setattr(chat_service, "_client", lambda _: FakeClient(text=private_marker))
    try:
        with caplog.at_level("INFO", logger="uvicorn.error"):
            with pytest.raises(Exception):
                review_video(video_id, "What do you see?")
        assert "gemini_review" in caplog.text
        assert private_marker not in caplog.text
        assert "What do you see?" not in caplog.text
        assert stored_counts(video_id) == (0, 0)
    finally:
        remove_video(video_id)


def test_provider_failure_and_nonready_video_save_nothing(monkeypatch):
    ready_id = make_ready_video()
    processing_id = make_ready_video()
    with SessionLocal() as db:
        processing = db.get(Video, processing_id)
        processing.ai_status = "PROCESSING"
        db.commit()

    calls = []
    monkeypatch.setattr(
        chat_service,
        "_client",
        lambda _: FakeClient(exception=RuntimeError("private provider detail")),
    )
    try:
        with TestClient(app) as client:
            failed = client.post(
                f"/api/videos/{ready_id}/chat", json={"message": "Review this"}
            )
            assert failed.status_code == 502
            assert "private provider detail" not in failed.text

            monkeypatch.setattr(
                chat_service,
                "_client",
                lambda _: calls.append("called"),
            )
            not_ready = client.post(
                f"/api/videos/{processing_id}/chat", json={"message": "Review this"}
            )
            assert not_ready.status_code == 409
            assert calls == []
        assert stored_counts(ready_id) == (0, 0)
        assert stored_counts(processing_id) == (0, 0)
    finally:
        remove_video(ready_id)
        remove_video(processing_id)


def test_review_context_includes_pdf_only_for_mrq(tmp_path: Path):
    brandbook = tmp_path / "brand.pdf"
    brandbook.write_bytes(b"%PDF-1.4 private brand guide")
    general = SimpleNamespace(
        gemini_file_uri="https://gemini.invalid/general",
        duration_ms=10_000,
        brand_context="NONE",
    )
    mrq = SimpleNamespace(
        gemini_file_uri="https://gemini.invalid/mrq",
        duration_ms=10_000,
        brand_context="MRQ",
    )

    general_contents = build_review_contents(general, [], [], "Question", tmp_path / "missing")
    mrq_contents = build_review_contents(mrq, [], [], "Question", brandbook)
    assert len(general_contents) == 2
    assert len(mrq_contents) == 2
    assert len(general_contents[0].parts) == 3
    assert len(mrq_contents[0].parts) == 4
    assert mrq_contents[0].parts[1].inline_data.mime_type == "application/pdf"
    assert "General review" in general_contents[0].parts[1].text
    assert "MRQ review" in mrq_contents[0].parts[2].text
