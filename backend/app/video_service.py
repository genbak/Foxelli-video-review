import json
import subprocess
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import Video


def probe_video(path: Path) -> int:
    invalid = AppError(422, "invalid_media", "Use an MP4 with H.264 video and AAC audio (or no audio).")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired:
        raise AppError(422, "invalid_media", "The video could not be validated within 20 seconds.") from None
    if result.returncode:
        raise invalid
    try:
        info = json.loads(result.stdout)
        container = info["format"]
        streams = info["streams"]
        video = [s for s in streams if s["codec_type"] == "video"]
        audio = [s for s in streams if s["codec_type"] == "audio"]
        # ffprobe groups MOV and MP4 together; reject QuickTime's container brand.
        if ("mp4" not in container["format_name"].split(",")
            or container.get("tags", {}).get("major_brand", "").strip() in ("", "qt")
            or len(video) != 1 or video[0].get("codec_name") != "h264"
            or video[0].get("pix_fmt") not in ("yuv420p", "yuvj420p")
            or any(s.get("codec_name") != "aac" for s in audio)):
            raise invalid
        seconds = Decimal(container["duration"])
        if not seconds.is_finite() or seconds <= 0:
            raise invalid
        duration = int((seconds * 1000).to_integral_value(rounding=ROUND_CEILING))
    except (KeyError, ValueError, TypeError, InvalidOperation):
        raise invalid from None
    if duration > get_settings().max_duration_ms:
        raise AppError(422, "video_too_long", "The video must be no longer than five minutes.")
    return duration


def store_video(file: UploadFile, context: str, db: Session) -> Video:
    settings = get_settings()
    staging = settings.upload_dir / "staging"
    media = settings.upload_dir / "media"
    staging.mkdir(parents=True, exist_ok=True, mode=0o700)
    media.mkdir(parents=True, exist_ok=True)
    key = f"{uuid4()}.mp4"
    partial = staging / f"{key}.part"
    published = media / key
    saved = False
    try:
        name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not name.lower().endswith(".mp4") or len(name) > 255:
            raise AppError(422, "invalid_media", "Choose an MP4 file with a filename up to 255 characters.")
        size = 0
        with partial.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise AppError(413, "upload_too_large", "The video must be 100 MiB or smaller.")
                output.write(chunk)
        if not size:
            raise AppError(422, "invalid_media", "The selected file is empty.")
        duration = probe_video(partial)
        partial.replace(published)
        video = Video(original_filename=name, storage_key=key, mime_type="video/mp4",
                      byte_size=size, duration_ms=duration, brand_context=context)
        db.add(video)
        db.commit()
        saved = True
        return video
    finally:
        file.file.close()
        partial.unlink(missing_ok=True)
        if not saved:
            published.unlink(missing_ok=True)
