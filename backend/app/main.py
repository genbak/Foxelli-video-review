from contextlib import asynccontextmanager
import logging
from typing import Annotated
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.config import get_settings
from app.chat_service import review_video
from app.db import engine, get_db
from app.errors import AppError
from app.gemini_service import (
    expire_provider_file_if_needed,
    prepare_video,
    recover_interrupted_preparations,
)
from app.models import Comment, Message, Video
from app.schemas import (
    BrandContext,
    ChatRequest,
    ChatResponse,
    CommentCreate,
    CommentRead,
    VideoRead,
)
from app.video_service import store_video

redis_client = Redis.from_url(
    get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    recover_interrupted_preparations()
    yield
    redis_client.close()
    engine.dispose()


app = FastAPI(title="Foxelli Video Review", lifespan=lifespan)
logger = logging.getLogger(__name__)
Database = Annotated[Session, Depends(get_db)]


@app.exception_handler(AppError)
async def app_error(request, exc: AppError):
    return JSONResponse(exc.body(), status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc: RequestValidationError):
    error = exc.errors()[0]
    field = str(error["loc"][-1])
    return JSONResponse(
        {"code": "invalid_input", "message": f"{field}: {error['msg']}", "retryable": False},
        status_code=422,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("Database operation failed (%s)", type(exc).__name__)
    return JSONResponse(
        {"code": "database_unavailable", "message": "The database is unavailable. Please try again.", "retryable": True},
        status_code=503,
    )


@app.exception_handler(OSError)
async def storage_error(request, exc):
    logger.error("Local storage operation failed (%s)", type(exc).__name__)
    return JSONResponse(
        {"code": "storage_unavailable", "message": "Video storage is unavailable. Please try again.", "retryable": True},
        status_code=503,
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        {"code": "request_error", "message": str(exc.detail), "retryable": False},
        status_code=exc.status_code,
    )


def find_video(video_id: UUID, db: Session) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "video_not_found", "This video was not found. Upload a video to start a review.")
    return video


def video_response(
    video: Video, comments: list[Comment], messages: list[Message]
) -> VideoRead:
    return VideoRead(
        id=video.id,
        original_filename=video.original_filename,
        mime_type=video.mime_type,
        byte_size=video.byte_size,
        duration_ms=video.duration_ms,
        brand_context=video.brand_context,
        ai_status=video.ai_status,
        ai_error=video.ai_error,
        created_at=video.created_at,
        media_url=f"/media/{video.storage_key}",
        comments=comments,
        messages=messages,
    )


def load_comments(video_id: UUID, db: Session) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.video_id == video_id)
            .order_by(Comment.timestamp_ms, Comment.created_at, Comment.id)
        )
    )


def load_messages(video_id: UUID, db: Session) -> list[Message]:
    return list(
        db.scalars(
            select(Message).where(Message.video_id == video_id).order_by(Message.id)
        )
    )


@app.post("/api/videos", status_code=202, response_model=VideoRead)
def upload_video(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Database,
    brand_context: Annotated[BrandContext, Form()] = "NONE",
):
    video = store_video(file, brand_context, db)
    background_tasks.add_task(prepare_video, video.id)
    return video_response(video, [], [])


@app.get("/api/videos/{video_id}", response_model=VideoRead)
def get_video(video_id: UUID, db: Database):
    video = find_video(video_id, db)
    expire_provider_file_if_needed(video, db)
    return video_response(video, load_comments(video.id, db), load_messages(video.id, db))


@app.post("/api/videos/{video_id}/prepare", status_code=202, response_model=VideoRead)
def retry_preparation(video_id: UUID, background_tasks: BackgroundTasks, db: Database):
    video = find_video(video_id, db)
    expire_provider_file_if_needed(video, db)
    if video.ai_status == "PROCESSING":
        raise AppError(409, "preparation_in_progress", "This video is already being prepared.")
    if video.ai_status == "READY":
        raise AppError(409, "video_already_ready", "This video is already ready for AI review.")

    result = db.execute(
        update(Video)
        .where(Video.id == video.id, Video.ai_status == "FAILED")
        .values(
            ai_status="PROCESSING",
            ai_error=None,
            gemini_file_name=None,
            gemini_file_uri=None,
            gemini_file_expires_at=None,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise AppError(409, "preparation_in_progress", "This video preparation already changed. Refresh and try again.")
    db.commit()
    db.refresh(video)
    background_tasks.add_task(prepare_video, video.id)
    return video_response(video, load_comments(video.id, db), load_messages(video.id, db))


@app.post("/api/videos/{video_id}/comments", status_code=201, response_model=CommentRead)
def create_comment(video_id: UUID, data: CommentCreate, db: Database):
    video = find_video(video_id, db)
    if data.timestamp_ms > video.duration_ms:
        raise AppError(422, "timestamp_out_of_range", "The comment timestamp must be within the video duration.")
    comment = Comment(video_id=video.id, timestamp_ms=data.timestamp_ms, text=data.text, author="HUMAN")
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@app.delete("/api/videos/{video_id}/comments/{comment_id}", status_code=204)
def delete_comment(video_id: UUID, comment_id: UUID, db: Database):
    find_video(video_id, db)
    comment = db.get(Comment, comment_id)
    if comment is None or comment.video_id != video_id:
        raise AppError(404, "comment_not_found", "This comment was not found on the video.")
    db.delete(comment)
    db.commit()


@app.post("/api/videos/{video_id}/chat", status_code=201, response_model=ChatResponse)
def create_chat_response(video_id: UUID, data: ChatRequest):
    return review_video(video_id, data.message)


@app.get("/api/health")
def health():
    checks = {"postgres": False, "redis": False}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(redis_client.ping())
    except Exception:
        pass
    ready = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )
