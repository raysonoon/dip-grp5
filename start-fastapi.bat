@echo off
setlocal EnableExtensions EnableDelayedExpansion
title DIP Group 5 - FastAPI Launcher

set "PROJECT_DIR=%~dp0"
set "API_DIR=%PROJECT_DIR%apps\api"
set "PYTHON_EXE=%API_DIR%\.venv\Scripts\python.exe"
set "DOCS_URL=http://127.0.0.1:8000/docs"
set "OPENAPI_URL=http://127.0.0.1:8000/openapi.json"
set "DOCKER_EXE="
set "DOCKER_DESKTOP="
set "ERR_MSG="

echo [1/7] Checking the project environment...
if not exist "%API_DIR%\compose.yaml" goto missing_project
if not exist "%PYTHON_EXE%" goto missing_python

echo       Installing Python dependencies...
"%PYTHON_EXE%" -m pip install -r "%API_DIR%\requirements.txt"
if errorlevel 1 goto pip_failed

for /f "delims=" %%D in ('where docker.exe 2^>nul') do if not defined DOCKER_EXE set "DOCKER_EXE=%%D"
if not defined DOCKER_EXE if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" set "DOCKER_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
if not defined DOCKER_EXE if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
if not defined DOCKER_EXE goto missing_docker

if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" set "DOCKER_DESKTOP=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
if not defined DOCKER_DESKTOP if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"

echo [2/7] Checking Docker Desktop...
"%DOCKER_EXE%" info >nul 2>&1 && goto docker_ready
if not defined DOCKER_DESKTOP goto docker_not_running

echo       Starting Docker Desktop. This can take a minute after boot...
start "" "%DOCKER_DESKTOP%"
for /l %%I in (1,1,180) do (
    "%DOCKER_EXE%" info >nul 2>&1 && goto docker_ready
    ping 127.0.0.1 -n 2 >nul
)
goto docker_timeout

:docker_ready
echo [3/7] Starting PostgreSQL and pgvector...
pushd "%API_DIR%"
"%DOCKER_EXE%" compose up -d --build
if errorlevel 1 goto compose_failed

echo [4/7] Waiting for PostgreSQL...
for /l %%I in (1,1,90) do (
    "%DOCKER_EXE%" compose exec -T db pg_isready >nul 2>&1 && goto database_ready
    ping 127.0.0.1 -n 2 >nul
)
goto database_timeout

:database_ready
echo [5/7] Applying migrations and confirming development data...
"%PYTHON_EXE%" -m alembic upgrade head
if errorlevel 1 goto migration_failed
"%PYTHON_EXE%" -m app.db.seed
if errorlevel 1 goto seed_failed

echo [6/7] Chatbot knowledge base (optional)...
echo       Skipped automatically. To (re)build the RAG knowledge base, run:
echo         python -m app.db.reindex
echo       (from apps\api; requires GEMINI_API_KEY in apps\api\.env).

echo [7/7] Starting FastAPI...
call :api_is_ready
if not errorlevel 1 goto open_docs

rem Keep the server's own window open when it crashes, so the traceback stays readable.
start "DIP FastAPI Server" /D "%API_DIR%" cmd /d /s /c "call "%PYTHON_EXE%" -m fastapi dev app\main.py || (echo. & echo [ERROR] FastAPI server exited with an error. See the traceback above. & pause)"
for /l %%I in (1,1,60) do (
    call :api_is_ready
    if not errorlevel 1 goto open_docs
    ping 127.0.0.1 -n 2 >nul
)
goto api_timeout

:open_docs
echo       FastAPI is ready at %DOCS_URL%
start "" "%DOCS_URL%"
popd
ping 127.0.0.1 -n 3 >nul
exit /b 0

:api_is_ready
"%PYTHON_EXE%" -c "import json, sys, urllib.request; document = json.load(urllib.request.urlopen('%OPENAPI_URL%', timeout=2)); sys.exit(0 if document.get('info', {}).get('title') == 'NTU Foodie Hub API' else 1)" >nul 2>&1
exit /b %errorlevel%

:pip_failed
set "ERR_MSG=Failed to install Python dependencies."
goto fail

:missing_project
set "ERR_MSG=Cannot find apps\api\compose.yaml under: %PROJECT_DIR%"
goto fail

:missing_python
set "ERR_MSG=The Python virtual environment is missing: %PYTHON_EXE% (run the project setup first)."
goto fail

:missing_docker
set "ERR_MSG=Docker CLI was not found. Install or repair Docker Desktop."
goto fail

:docker_not_running
set "ERR_MSG=Docker is not running and Docker Desktop could not be located."
goto fail

:docker_timeout
set "ERR_MSG=Docker Desktop did not become ready within 180 seconds."
goto fail

:compose_failed
set "ERR_MSG=Docker Compose could not start the database."
goto fail_popd

:database_timeout
set "ERR_MSG=PostgreSQL did not become ready within 90 seconds."
goto fail_popd

:migration_failed
set "ERR_MSG=Database migration failed."
goto fail_popd

:seed_failed
set "ERR_MSG=Development data setup failed."
goto fail_popd

:api_timeout
set "ERR_MSG=FastAPI did not become ready within 60 seconds (see the DIP FastAPI Server window)."
goto fail_popd

:fail_popd
popd

:fail
echo.
echo [ERROR] %ERR_MSG%
echo.
pause
exit /b 1
