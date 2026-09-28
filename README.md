# Foxelli Video Review

Upload a video ad, get timestamped Gemini feedback, then review it alongside your own comments. The app keeps the video, selected brand context and conversation together.

The review and chat use the actual video at 5 FPS and high media resolution, with one Gemini call per request. The prompts live in [backend/app/prompts.py](backend/app/prompts.py).

## Stack

Next.js/TypeScript, FastAPI, PostgreSQL, Redis and Nginx run through Docker Compose. The backend uses SQLAlchemy/Alembic and the Google Gen AI SDK. Redis supplies a readiness check; it is not a queue or cache.

## Setup

You need Docker with Linux containers, a Gemini API key with access to `gemini-3.8-flash`, and the supplied Mrs. Quilty PDF.

Place the PDF at this path before starting Compose:

```text
references/private/brand/MRQ-brandbook-July-2024.pdf
```

The PDF stays outside Git. Compose mounts it read-only, and only MRQ requests send it to Gemini. General requests omit it.

On Windows:

```powershell
Copy-Item .env.example .env
# Set GEMINI_API_KEY and replace POSTGRES_PASSWORD in .env.
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8080/api/health
```

On Linux, use `cp .env.example .env` and `curl --fail http://localhost:8080/api/health` instead.

Open [localhost:8080](http://localhost:8080). The health response should show `status: ready`, with PostgreSQL and Redis both `true`. Only Nginx binds a host port.

## Using the app

1. Select General or MRQ and upload an MP4.
2. Wait for preparation to finish, then click **Review full video**.
3. Click a comment to pause and seek to its timestamp.
4. Add Human comments beneath the player or discuss the edit in **AI chat**. Use **Remove** on any comment you want to discard. Ask chat to revise or remove a specific AI comment when needed.

Press Enter to send a chat message, or Shift+Enter for a new line.

The app does not generate feedback automatically on upload. Playback and Human comments work while preparation runs. Failed or expired preparation has a manual retry option.

Context is fixed at upload. Upload the file again to review it under a different context. Reviews survive reloads through `/?video=<id>`; PostgreSQL and media use persistent Docker volumes.

Accepted input: one H.264/yuv420 video stream in MP4, with AAC audio or no audio, up to 100 MiB and five minutes. The app validates the original file; it does not transcode.

## Checks

Run tests against a local or disposable database, not a live deployment. App startup marks interrupted preparation as failed.

```powershell
docker compose run --rm backend python -m pytest -q
docker compose build frontend
docker compose config --quiet
```

The backend tests cover media validation, preparation, General/MRQ isolation, review/chat behavior, comment changes, timestamp limits and atomic persistence. They mock Gemini and do not make paid model calls. The frontend Docker build runs TypeScript checks and the production build.

## How AI feedback is saved

Each request includes the video, all saved comments, up to 20 recent messages and the latest request. MRQ adds the complete brand-book PDF.

Gemini returns a message and optional comment actions. When explicitly asked, it can add, revise or remove its own comments; it cannot alter Human comments. The backend checks response completion, schema, target ownership and timestamp ranges before saving everything in one transaction. An invalid response saves no partial feedback.

## Limits

Gemini can miss important concerns or overstate visual/audio details. Check its comments against the video. Schema validation checks data shape, not whether an observation is true, and 5 FPS is not every-frame inspection.

General/HN reviews have no authoritative brand guide. The prompt includes five supplied style examples, so results on the supplied videos are not a held-out accuracy benchmark.

This app has shared data, no user accounts and no per-user isolation. If a response is lost, check the saved review before resending. Hosting needs HTTPS and an access gate. Deployment, browser verification and the Loom recording remain separate delivery steps.

## Files

- `frontend/`: review interface
- `backend/`: API, database migrations, Gemini integration, prompts and automated tests
- `nginx/`: routing and byte-range video delivery
- [Architecture](docs/ARCHITECTURE.md): components, lifecycle and API
- [Prompt design](docs/PROMPTS.md): instructions, input and output contract
- [Deployment](docs/DEPLOYMENT.md): server setup and verification
- `references/`: private PDF setup instructions

The repo excludes credentials, client PDFs, videos, private evaluations and development notes.
