# Architecture

## Runtime

```text
Browser
  |
Nginx
  |-- /         -> Next.js
  |-- /api/*    -> FastAPI
  `-- /media/*  -> validated video volume
                       ^
                       | writes
                    FastAPI
                       |-- PostgreSQL: videos, comments, messages
                       |-- Redis: readiness
                       `-- Gemini: video preparation and review/chat
```

The application runs as five Docker Compose services: Nginx, frontend, backend, PostgreSQL and Redis. Only Nginx is exposed to the host. Redis is a readiness dependency, not a queue or application-data store.

## Review lifecycle

1. FastAPI streams an upload into staging, enforces the size limit and uses `ffprobe` to validate the container, codecs and duration.
2. The validated original is stored under a generated name in a Docker volume. Metadata and the selected General/MRQ context are stored in PostgreSQL.
3. A background preparation task uploads the original through the Gemini Files API and records its reusable provider reference and expiry.
4. The browser polls preparation status. Playback and Human comments remain available while preparation runs.
5. A user-triggered review sends the prepared video, saved context and conversation to Gemini. MRQ requests also include the private brand-book PDF.
6. The backend validates the structured response before saving messages and comment changes in one transaction.

Provider files are temporary, so the validated local original remains the recovery source. Failed or expired preparation can be retried manually.

## Persistence

- `videos`: local media metadata, selected context and Gemini preparation state
- `comments`: timestamped Human or AI feedback
- `messages`: ordered user and assistant chat history

PostgreSQL and uploaded video files use named Docker volumes. Redis has no persistent application data. A review is restored through `/?video=<uuid>`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | PostgreSQL and Redis readiness |
| `POST /api/videos` | Validate, store and schedule preparation |
| `GET /api/videos/{id}` | Return review metadata, state and feedback |
| `POST /api/videos/{id}/prepare` | Retry failed or expired preparation |
| `POST /api/videos/{id}/comments` | Save one Human comment |
| `DELETE /api/videos/{id}/comments/{comment_id}` | Remove a Human or AI comment |
| `POST /api/videos/{id}/chat` | Run review/chat and atomically save valid output |
| `GET /media/{storage_key}` | Nginx byte-range media delivery |

Errors return a stable `code`, user-safe `message` and `retryable` flag. Provider identifiers, local paths, prompts and secrets are backend-only.

## Gemini request

The backend uses the official Google Gen AI SDK directly. Each request contains the video at 5 FPS/high media resolution, verified duration and context, all saved comments, up to 20 recent messages and the current user request. MRQ requests additionally contain the full visual PDF; General requests do not.

The structured response contains a message and zero to ten comment actions. Ten is a safety ceiling, not a requested number. New comments need valid text and an in-range timestamp; revisions may change the text or timestamp of an existing AI comment; removals target an existing AI comment. AI actions cannot change Human comments. Persistence occurs only after the complete response passes validation.

## Security boundaries

- `.env`, API keys, credentials, private PDFs and uploaded media are excluded from Git.
- The MRQ PDF is mounted read-only and is never served by Next.js or Nginx.
- Database, Redis, frontend and backend ports are private to the Compose network.
- Uploaded filenames are never used as storage paths.
- Nginx exposes media by generated storage key with directory listing disabled.

The current application has no user accounts or per-user isolation. A hosted instance should therefore sit behind HTTPS and an access gate appropriate to the deployment environment.
