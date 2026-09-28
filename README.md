# PhotoSpace

Phase 0 foundation for PhotoSpace, a photo-grounded interior redesign project.
This repository contains the shared schemas, the Postgres tables, a FastAPI health check, and a Next.js page that displays that check.

## Setup

Python 3.11.9, uv, Docker, and Node.js are required.

```bash
cp .env.example .env
uv sync --all-groups
docker compose up -d
uv run alembic upgrade head
```

## Run

API, on port 8001:

```bash
uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001
```

Frontend, from `frontend/`:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. The page reads `API_URL` and shows the `/health` response.

## Tests

```bash
uv run pytest
uv run ruff check .
```
