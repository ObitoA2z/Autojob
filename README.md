# AutoInfluence

Systeme d'automatisation pour postuler a des campagnes d'influence multi-plateformes.

## Architecture
- `backend/`: FastAPI + PostgreSQL models + services
- `agents/`: scheduler/agent runtime
- `platforms/`: connecteurs marketplaces (reachr, modash, upfluence, collabstr, aspire)
- `automation/`: OpenClaw + fallback Playwright
- `ai/`: generation de message de candidature
- `frontend/`: Next.js dashboard minimal
- `scripts/`: scripts utilitaires (scanner, agent)
- `alembic/`: migrations de schema

## Setup
1. Copier `.env.example` en `.env` et adapter les valeurs.
2. Lancer Postgres + Redis:
   - `docker compose up -d`
3. Installer dependances Python:
   - `pip install -r requirements.txt`
4. Installer Playwright Chromium:
   - `playwright install chromium`
5. Appliquer les migrations:
   - `alembic upgrade head`

## Run Backend
- `uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`

## Run Worker
- `celery -A backend.celery_app.celery_app worker --loglevel=info`

## Run Scanner
- `python scripts/run_scanner.py`

## Run Agent Scheduler
- `python scripts/start_agent.py`

## Run Frontend
1. `cd frontend`
2. `npm install`
3. `npm run dev`

Set frontend API target with `NEXT_PUBLIC_API_URL`, default `http://127.0.0.1:8000/api`.

## API Endpoints
- `GET /api/health`
- `GET /api/stats`
- `GET /api/campaigns`
- `GET /api/applications`
- `PATCH /api/applications/{application_id}/status?status=replied`
- `GET /api/profile`
- `POST /api/profile`
- `PATCH /api/profile`
- `PUT /api/profile`
- `POST /api/scan`
- `POST /api/scan/async`
- `POST /api/apply/{campaign_id}`
- `POST /api/apply/{campaign_id}/async`
- `GET /api/tasks/{task_id}`

## Notes OpenClaw
The project calls OpenClaw through `automation/openclaw_client.py`.
If OpenClaw is unavailable, it falls back to Playwright.

## Notes Collabstr
`platforms/collabstr.py` includes a real connector flow:
- OpenClaw-first actions (`collabstr_login`, `collabstr_scan`, `collabstr_submit`)
- Playwright fallback with resilient selector lists for login/scan/submit
- session persistence (`COLLABSTR_STORAGE_STATE_PATH`)
- campaign extraction from both OpenClaw payload and Next.js page data
