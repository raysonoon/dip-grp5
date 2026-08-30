# Week 3 Backend Environment Update Guide

This guide is for team members who have already run the previous backend version.

Use this guide only after the Week 3 backend changes have been committed and pushed to the branch your team will use.

Before starting, make sure Docker Desktop is running. Do not delete or replace the existing `.env` file, and do not delete the Docker volume. The old `.env` contains the password required to connect to the existing database.

## Windows

Open PowerShell in the project folder.

### 1. Get the latest code

```powershell
git switch main
git pull origin main
cd apps\api
```

If the update is provided on another branch, replace `main` with that branch name. Commit or save your own local changes before pulling.

### 2. Update the Python environment

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `.venv` no longer exists:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Update `.env`

Keep the existing PostgreSQL password and `DATABASE_URL`. Add or update these lines:

```env
SEED_ADMIN_DISPLAY_NAME=Administrator
SEED_ADMIN_EMAIL_ADDRESS=admin@local.invalid
SEED_ADMIN_PASSWORD=admin
SEED_TEST_DISPLAY_NAME=Test User
SEED_TEST_EMAIL_ADDRESS=test-user@local.invalid
SEED_TEST_PASSWORD=test
DEV_AUTH_ENABLED=true
```

Old `SEED_ADMIN_USERNAME` and `SEED_TEST_USERNAME` lines can be removed.

### 4. Start and update the database

```powershell
docker compose up -d
docker compose ps
```

Do not continue until `docker compose ps` shows the database status as `healthy`. If it still shows `starting`, wait a few seconds and run `docker compose ps` again.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.db.seed
```

### 5. Verify and start the backend

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m fastapi dev app\main.py
```

Open <http://127.0.0.1:8000/docs>.

## macOS

Open Terminal in the project folder.

### 1. Get the latest code

```bash
git switch main
git pull origin main
cd apps/api
```

If the update is provided on another branch, replace `main` with that branch name. Commit or save your own local changes before pulling.

### 2. Update the Python environment

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

If `.venv` no longer exists:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

### 3. Update `.env`

Keep the existing PostgreSQL password and `DATABASE_URL`. Add or update these lines:

```env
SEED_ADMIN_DISPLAY_NAME=Administrator
SEED_ADMIN_EMAIL_ADDRESS=admin@local.invalid
SEED_ADMIN_PASSWORD=admin
SEED_TEST_DISPLAY_NAME=Test User
SEED_TEST_EMAIL_ADDRESS=test-user@local.invalid
SEED_TEST_PASSWORD=test
DEV_AUTH_ENABLED=true
```

Old `SEED_ADMIN_USERNAME` and `SEED_TEST_USERNAME` lines can be removed.

### 4. Start and update the database

```bash
docker compose up -d
docker compose ps
```

Do not continue until `docker compose ps` shows the database status as `healthy`. If it still shows `starting`, wait a few seconds and run `docker compose ps` again.

```bash
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python -m app.db.seed
```

### 5. Verify and start the backend

```bash
./.venv/bin/python -m alembic current
./.venv/bin/python -m pytest -q
./.venv/bin/python -m fastapi dev app/main.py
```

Open <http://127.0.0.1:8000/docs>.

## Expected Result

- Alembic revision: `g5b7c9d1e3f4 (head)`
- Test result: `18 passed`
- Seed result: 59 Chatbot questions
- PostgreSQL port: `5433`

The migration keeps existing users, reviews, vendors, and images. The seed adds or confirms the development accounts, demo vendors, and Chatbot questions without creating duplicates.

## Important

Do not run `docker compose down --volumes` or delete the `dip-grp5-pgdata` Docker volume. Doing so deletes the existing local PostgreSQL data.
