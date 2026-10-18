# AGENTS.md

NTU Foodie Hub: FastAPI backend (`apps/api`) + Vite/React SPA (`apps/web`).
There is no root workspace or package manager — run every command from inside
the relevant app directory.

## Commands

Run backend commands from `apps/api` with `.venv` active; frontend from `apps/web`.

Backend:
- `python -m fastapi dev app/main.py` — dev API on :8000
- `python -m pytest -q` — full suite runs on in-memory SQLite (see `tests/conftest.py`); Docker/Postgres not needed
- `$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:change_me@127.0.0.1:5433/dip_grp5"; python -m pytest -q -m vector` — pgvector integration tests (skipped without `TEST_DATABASE_URL`)
- `python -m alembic upgrade head` / `python -m app.db.seed` / `python -m app.db.reindex` (reindex needs `GEMINI_API_KEY`)

Frontend:
- `npm run dev` — Vite on :5173; proxies `/auth /preferences /chat /reviews /vendors /media` to :8000, so start the API first
- `npm test` — Node test runner over an **explicit file list** in `package.json`. New `*.test.js` files are not auto-discovered; add them to the `test` script. (`src/lib/locationBoundaries.test.js` is currently missing from it.)
- `npm run build` — `vite build` only; it does **not** typecheck (no `tsc`, and tsconfig is `noEmit`). There is no typecheck script.
- `npm run lint:fix` is the only ESLint script — the README's `npm run lint` does not exist.

One-click local launcher (repo root, Windows/macOS): `.\start-fastapi.bat` / `./start-fastapi.sh`
runs Docker + migrations + seed + `fastapi dev`.

## Backend notes

- Wiring: `app/main.py` registers routers from `app/api/routes/`; models in `app/models/`, DTOs in `app/schemas/`, RAG pipeline in `app/services/`.
- Alembic autogenerate targets **two** metadata objects (`Base` and `VectorBase`) — see `alembic/env.py`. pgvector tables (e.g. `knowledge_chunks`) must subclass `VectorBase` (`app/db/vector_base.py`), otherwise SQLite test schemas try to create the `vector` column type and fail. The DB URL comes from `settings.database_url`, not `alembic.ini`.
- Local Postgres comes from `apps/api/compose.yaml` (pgvector build, container `dip-grp5-postgres`, host port **5433**, not 5432). Run `docker compose` from `apps/api` so `.env` is loaded.
- `app/db/seed.py` is idempotent. It imports `data/knowledge_chunks.csv` only when `knowledge_chunks` is empty, resolving `vendor_id` from the already-seeded Google/Reddit rows, so local IDs may differ from the CSV.
- Auth = Supabase bearer tokens verified via JWKS (`app/api/dependencies.py`, `app/core/security.py`). `get_current_user` links or creates a local user by `supabase_user_id` / `email_canonical`. `tests/conftest.py` overrides these deps and treats the bearer token as the integer user id. The README's "temporary local auth" / "dev auth" wording is stale.
- Reviewed internal vendor averages are kept in sync by a database trigger; `average_google_rating` is a separate field.

## Frontend notes

- Mixed JS/TS on purpose (`allowJs: true`): API clients and helpers are `.js`, pages/components are `.tsx`. `@/` aliases `src/`.
- Data is fetched live from the API (no test fixtures); seed the database before expecting vendor/review IDs.

## Docs

- `README.md` — setup + API reference (accurate except the `npm run lint` script)
- `docs/db-schema.md` — database tables reference; `docs/chatbot.md` — RAG design notes
