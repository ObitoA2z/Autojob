# Repository Audit (2026-03-10)

## Summary
The repository previously implemented an automatic **job application** system for classic job boards. It did not match the requested scope (influencer campaign marketplaces).

## Module Decisions

### KEEP
- `requirements.txt` (concept only): dependency management pattern retained and updated.

### MODIFY
- `ai/*` -> replaced by `ai/generator.py` for influencer application messages.
- `database.py` -> replaced by modular SQLAlchemy setup in `backend/database/` with PostgreSQL support.
- `main.py` -> replaced by modular FastAPI app in `backend/main.py` and router/service layers.

### DELETE
- `scrapers/*`: employment websites (Indeed, APEC, etc.), outside influencer scope.
- `static/*` and `templates/*`: old monolithic frontend replaced by Next.js app.
- `applicator/*`: empty/non-usable module.
- `start.sh`, `start.bat`: tied to previous architecture.
- `scrapers/contact_finder.py`: broken (syntax errors; could not compile).

## Detected Issues In Legacy Code
- Monolithic architecture (routing + scraping + AI + persistence mixed).
- Data model mismatch (jobs/offers instead of campaigns/applications).
- Runtime risk: at least one syntax-breaking module in scrapers.
- Weak extensibility for adding new platforms.

## Result
Repository refactored to campaign automation architecture:
- FastAPI backend (`/backend`)
- OpenClaw + Playwright automation (`/automation`, `/agents`)
- Platform connector abstraction (`/platforms`)
- Real Collabstr connector flow (`/platforms/collabstr.py`)
- AI generator (`/ai`)
- Next.js dashboard (`/frontend`)
- Alembic migrations (`/alembic`)
- Worker scripts (`/scripts`)
