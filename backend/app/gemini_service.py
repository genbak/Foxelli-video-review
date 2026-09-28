import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from google import genai
from google.genai import errors, types
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Video

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Preparation was interrupted. Retry to continue."
EXPIRED_MESSAGE = "The prepared Gemini file expired. Retry preparation to continue."


class PreparationFailure(Exception):
    pass


def _client(timeout_seconds: int | None = None):
    settings = get_settings()
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=(timeout_seconds or settings.gemini_prepare_timeout_seconds) * 1000
        ),
    )


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, PreparationFailure):
        return str(exc)
    if isinstance(exc, errors.ClientError):
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return "Gemini could not authenticate. Check the server API key and retry."
        if code == 429:
            return "Gemini is temporarily rate limited. Retry in a moment."
        return "Gemini rejected this video preparation request. Please retry."
    if isinstance(exc, errors.ServerError):
        return "Gemini is temporarily unavailable. Please retry."
    if isinstance(exc, OSError):
        return "The saved video file is unavailable. Upload it again or retry."
    return "Gemini could not prepare this video. Please retry."


def _mark_failed(video_id: UUID, message: str) -> None:
    try:
        with SessionLocal() as db:
            db.execute(
                update(Video)
                .where(Video.id == video_id, Video.ai_status == "PROCESSING")
                .values(ai_status="FAILED", ai_error=message, updated_at=datetime.now(timezone.utc))
            )
            db.commit()
    except Exception as exc:
        logger.error(
            "Could not save failed Gemini preparation for video %s (%s)",
            video_id,
            type(exc).__name__,
        )


def prepare_video(video_id: UUID) -> None:
    client = None
    try:
        settings = get_settings()
        with SessionLocal() as db:
            video = db.get(Video, video_id)
            if video is None or video.ai_status != "PROCESSING":
                return
            path = settings.upload_dir / "media" / video.storage_key
            original_filename = video.original_filename

        if not path.is_file():
            raise OSError("saved media missing")

        client = _client()
        provider_file = client.files.upload(
            file=path,
            config=types.UploadFileConfig(
                mime_type="video/mp4",
                display_name=original_filename,
            ),
        )
        if not provider_file.name:
            raise PreparationFailure("Gemini did not return a usable file reference. Please retry.")

        with SessionLocal() as db:
            db.execute(
                update(Video)
                .where(Video.id == video_id, Video.ai_status == "PROCESSING")
                .values(
                    gemini_file_name=provider_file.name,
                    gemini_file_uri=provider_file.uri,
                    gemini_file_expires_at=provider_file.expiration_time,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            db.commit()

        deadline = time.monotonic() + settings.gemini_prepare_timeout_seconds
        while provider_file.state == types.FileState.PROCESSING and time.monotonic() < deadline:
            time.sleep(2)
            provider_file = client.files.get(name=provider_file.name)

        if provider_file.state == types.FileState.PROCESSING:
            raise PreparationFailure("Gemini did not finish preparing this video in time. Retry preparation.")
        if provider_file.state != types.FileState.ACTIVE or not provider_file.uri:
            raise PreparationFailure(
                "Gemini could not process this video. Try a compatible MP4 or retry preparation."
            )

        with SessionLocal() as db:
            db.execute(
                update(Video)
                .where(Video.id == video_id, Video.ai_status == "PROCESSING")
                .values(
                    ai_status="READY",
                    ai_error=None,
                    gemini_file_name=provider_file.name,
                    gemini_file_uri=provider_file.uri,
                    gemini_file_expires_at=provider_file.expiration_time,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
    except Exception as exc:
        logger.warning(
            "Gemini preparation failed for video %s (%s)", video_id, type(exc).__name__
        )
        _mark_failed(video_id, _safe_error(exc))
    finally:
        if client is not None:
            client.close()


def recover_interrupted_preparations() -> None:
    with SessionLocal() as db:
        db.execute(
            update(Video)
            .where(Video.ai_status == "PROCESSING")
            .values(
                ai_status="FAILED",
                ai_error=INTERRUPTED_MESSAGE,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


def expire_provider_file_if_needed(video: Video, db: Session) -> None:
    expires_at = video.gemini_file_expires_at
    if video.ai_status != "READY" or expires_at is None:
        return
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        video.ai_status = "FAILED"
        video.ai_error = EXPIRED_MESSAGE
        video.gemini_file_name = None
        video.gemini_file_uri = None
        video.gemini_file_expires_at = None
        db.commit()

