@echo off
setlocal EnableExtensions EnableDelayedExpansion
title DIP Group 5 - FastAPI Launcher

set "PROJECT_DIR=%~dp0"
set "API_DIR=%PROJECT_DIR%apps\api"
set "PYTHON_EXE=%API_DIR%\.venv\Scripts\python.exe"
set "DOCS_URL=http://127.0.0.1:8000/docs"
set "DOCKER_EXE="
set "DOCKER_DESKTOP="

echo [1/6] Checking the project environment...
if not exist "%API_DIR%\compose.yaml" goto missing_project
if not exist "%PYTHON_EXE%" goto missing_python

for /f "delims=" %%D in ('where docker.exe 2^>nul') do if not defined DOCKER_EXE set "DOCKER_EXE=%%D"
if not defined DOCKER_EXE if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" set "DOCKER_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
if not defined DOCKER_EXE if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
if not defined DOCKER_EXE goto missing_docker

if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" set "DOCKER_DESKTOP=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
if not defined DOCKER_DESKTOP if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"

echo [2/6] Checking Docker Desktop...
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
echo [3/6] Starting PostgreSQL and pgvector...
pushd "%API_DIR%"
"%DOCKER_EXE%" compose up -d
if errorlevel 1 goto compose_failed

echo [4/6] Waiting for PostgreSQL...
for /l %%I in (1,1,90) do (
    "%DOCKER_EXE%" compose exec -T db pg_isready >nul 2>&1 && goto database_ready
    ping 127.0.0.1 -n 2 >nul
)
goto database_timeout

:database_ready
echo [5/6] Applying migrations and confirming development data...
"%PYTHON_EXE%" -m alembic upgrade head
if errorlevel 1 goto migration_failed
"%PYTHON_EXE%" -m app.db.seed
if errorlevel 1 goto seed_failed

echo [6/6] Starting FastAPI...
curl.exe --silent --fail --output NUL "%DOCS_URL%" >nul 2>&1
if not errorlevel 1 goto open_docs

start "DIP FastAPI Server" /D "%API_DIR%" "%PYTHON_EXE%" -m fastapi dev app\main.py
for /l %%I in (1,1,60) do (
    curl.exe --silent --fail --output NUL "%DOCS_URL%" >nul 2>&1 && goto open_docs
    ping 127.0.0.1 -n 2 >nul
)
goto api_timeout

:open_docs
echo       FastAPI is ready at %DOCS_URL%
start "" "%DOCS_URL%"
popd
ping 127.0.0.1 -n 3 >nul
exit /b 0

:missing_project
echo.
echo [ERROR] Cannot find apps\api\compose.yaml under:
echo         %PROJECT_DIR%
goto stop_with_error

:missing_python
echo.
echo [ERROR] The Python virtual environment is missing:
echo         %PYTHON_EXE%
echo         Run the project setup before using this launcher.
goto stop_with_error

:missing_docker
echo.
echo [ERROR] Docker CLI was not found. Install or repair Docker Desktop.
goto stop_with_error

:docker_not_running
echo.
echo [ERROR] Docker is not running and Docker Desktop could not be located.
goto stop_with_error

:docker_timeout
echo.
echo [ERROR] Docker Desktop did not become ready within 180 seconds.
goto stop_with_error

:compose_failed
echo.
echo [ERROR] Docker Compose could not start the database.
goto stop_with_error_popd

:database_timeout
echo.
echo [ERROR] PostgreSQL did not become ready within 90 seconds.
goto stop_with_error_popd

:migration_failed
echo.
echo [ERROR] Database migration failed.
goto stop_with_error_popd

:seed_failed
echo.
echo [ERROR] Development data setup failed.
goto stop_with_error_popd

:api_timeout
echo.
echo [ERROR] FastAPI did not become ready within 60 seconds.
goto stop_with_error_popd

:stop_with_error_popd
popd

:stop_with_error
echo.
pause
exit /b 1
