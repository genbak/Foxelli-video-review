# Deployment

The repository is packaged as one Docker Compose application. The same images and configuration used locally can run on a small Linux server.

## Required private inputs

Create `.env` from `.env.example` and provide:

- a strong `POSTGRES_PASSWORD`;
- `GEMINI_API_KEY`;
- the desired `GEMINI_MODEL`, if overriding the tested default; and
- an available host `APP_PORT`.

Place the supplied brand book at:

```text
references/private/brand/MRQ-brandbook-July-2024.pdf
```

Do not commit `.env` or the PDF. The Compose file mounts the PDF read-only at `/app/reference/mrq.pdf`.

## Start

```bash
cp .env.example .env
# Edit .env before continuing.
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8080/api/health
```

The default port is intentionally bound to `127.0.0.1`. For external access, place a host-managed HTTPS reverse proxy or private tunnel in front of `127.0.0.1:${APP_PORT}`. Add authentication because this version has no application accounts or per-user isolation. Do not expose PostgreSQL, Redis, FastAPI or Next.js directly.

## Persistent data

The `postgres_data` and `uploads` named volumes contain reviews and validated media. Normal restarts preserve them:

```bash
docker compose stop
docker compose up -d
```

Do not run `docker compose down --volumes` unless deleting all application data is intentional and a backup is not required.

## Update

```bash
git pull --ff-only
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/health
```

Run database migrations through the backend startup command supplied by its image. Review container logs if any health check fails:

```bash
docker compose logs --tail=200 backend frontend nginx postgres redis
```

## Pre-deployment verification

Run the backend suite against a local or disposable database, not the live deployment.

```bash
docker compose run --rm backend python -m pytest -q
docker compose build frontend
docker compose config --quiet
```

After deployment, verify upload, playback seeking, Human comments, one General review and one MRQ review. Confirm that MRQ works only when the private PDF is present and that a General review does not receive brand guidance.
