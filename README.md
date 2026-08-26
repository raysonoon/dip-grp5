# dip-grp5

## Folder structure
dip-grp-5/
├── package.json                          # Root orchestration & workspace scripts
├── package-lock.json
├── .prettierrc                           # Shared Prettier rules
├── .prettierignore                       # Ignore build dirs, python files, etc.
├── docker-compose.yml                    # Root Postgres (pgvector) container
├── .env.example                          # Root environment variable template
├── .gitignore
├── README.md
│
├── apps/
│   ├── api/                              # FastAPI Backend
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── api/
│   │   │   │   ├── dependencies.py
│   │   │   │   └── routes/
│   │   │   │       ├── reviews.py
│   │   │   │       └── vendors.py
│   │   │   ├── core/
│   │   │   │   ├── config.py
│   │   │   │   └── security.py
│   │   │   ├── db/
│   │   │   │   ├── alembic/              # Co-located migration environment
│   │   │   │   │   ├── versions/
│   │   │   │   │   ├── env.py
│   │   │   │   │   └── script.py.mako
│   │   │   │   ├── base.py
│   │   │   │   ├── seed.py
│   │   │   │   └── session.py
│   │   │   ├── models/
│   │   │   │   ├── review.py
│   │   │   │   ├── user.py
│   │   │   │   └── vendor.py
│   │   │   └── schemas/
│   │   │       ├── review.py
│   │   │       └── vendor.py
│   │   ├── docker/
│   │   │   └── init/
│   │   │       └── 01-enable-vector.sql
│   │   ├── docs/
│   │   │   ├── community-review-database-design.md
│   │   │   ├── community-review-erd.png
│   │   │   ├── community-review-erd.svg
│   │   │   └── tables/
│   │   ├── tests/
│   │   │   ├── test_create_review_api.py
│   │   │   ├── test_database_integration.py
│   │   │   ├── test_dev_auth.py
│   │   │   ├── test_model_metadata.py
│   │   │   └── test_vendor_api.py
│   │   ├── .venv/                        # Gitignored local virtual environment
│   │   ├── .env.example
│   │   ├── alembic.ini
│   │   ├── Manual.md
│   │   ├── pytest.ini
│   │   └── requirements.txt              # Ruff / Black / Flake8 configured here
│   │
│   └── web/                              # Vite + React (TS) SPA Frontend
│       ├── index.html
│       ├── package.json                  # App dependencies + ESLint/Prettier callers
│       ├── eslint.config.js              # App-specific ESLint config (extends workspace base)
│       ├── tsconfig.json
│       ├── tsconfig.node.json
│       ├── vite.config.ts                # Dev proxy settings
│       ├── public/
│       │   └── favicon.svg
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── App.css
│           ├── index.css
│           ├── vite-env.d.ts
│           ├── components/               # Shared / Atomic UI elements (Buttons, Modals)
│           ├── features/                 # Domain-driven feature modules
│           │   ├── reviews/              # Review UI, hooks, and sub-components
│           │   └── vendors/              # Vendor UI, hooks, and sub-components
│           ├── lib/                      # Axios/Fetch API client instances
│           ├── pages/                    # Router page view components
│           └── types/                    # Frontend TypeScript interfaces
│
└── packages/                             # Workspace shared packages
    └── config-eslint/                    # Centralized ESLint Flat Config package
        ├── package.json
        ├── base.js                       # Shared JS/TS rules
        └── react.js                      # React + Hooks + Vite plugin rules

## Project documentation

- [Backend setup and API manual](Manual.md)
- [Community review database design](docs/community-review-database-design.md)
- [Community review database ERD](docs/community-review-erd.svg)
- [Database tables reference](docs/tables/README.md)

## Local backend environment

Python 3.12 and Docker Desktop are used for local backend development.

### First-time setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Change the local-only database password in `.env`, then start PostgreSQL with
the pgvector extension:

```powershell
docker compose up -d
docker compose ps
```

Create or update the database tables, then seed the local placeholder data:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.db.seed
```

The repeatable seed command creates or confirms these local placeholders:

| Type | Name | Password/role |
| --- | --- | --- |
| Administrator | `admin` | password `admin`, role `admin` |
| Normal user | `test_user` | password `test`, role `user` |
| Food stall | `Demo Vendor 1` | `Demo Canteen` |
| Food stall | `Demo Vendor 2` | `Demo Canteen` |

Passwords are stored as Argon2 hashes. Running the seed command again does not
create duplicate placeholders. Its output shows the generated IDs.

### Temporary local authentication

Until the team integrates the real login system, a protected FastAPI route can
use the placeholder dependency:

```python
from app.api.dependencies import CurrentUser


def protected_route(user: CurrentUser):
    return {"user_id": user.id}
```

With `DEV_AUTH_ENABLED=true` in the local `.env`, the frontend or an API client
can choose a seeded user by sending its generated ID:

```text
X-Dev-User-Id: <seeded user ID>
```

This header is a development shortcut, not secure authentication. The example
environment keeps it disabled. Replace it with the team's real session or token
authentication and keep `DEV_AUTH_ENABLED=false` in every shared or deployed
environment.

## Run the API

Start FastAPI from the project root:

```powershell
.\.venv\Scripts\python.exe -m fastapi dev app\main.py
```

Open <http://127.0.0.1:8000/docs> to use the interactive API page.

### Create a review

`POST /reviews` accepts a food-stall ID, a required rating from 1.0 to 5.0 in
0.5-star steps, and an optional comment. Use the IDs printed by the seed script:

```powershell
$body = @{
    vendor_id = 2
    rating = 1
    comment = ""
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8000/reviews `
    -Headers @{ "X-Dev-User-Id" = "1" } `
    -ContentType "application/json" `
    -Body $body
```

The API takes `user_id` from the authenticated user header; it does not accept
`user_id` in the request body. An omitted or whitespace-only comment is stored
as `NULL`, so rating-only reviews are supported.

### Read reviews

Reading community reviews is public and does not require the temporary login
header:

```text
GET /reviews
GET /reviews/{review_id}
```

The list endpoint returns the newest reviews first. It supports:

| Query parameter | Default | Purpose |
| --- | ---: | --- |
| `vendor_id` | none | Return reviews for one food stall |
| `limit` | `20` | Number of reviews to return; maximum `100` |
| `offset` | `0` | Number of reviews to skip for pagination |

Example:

```text
http://127.0.0.1:8000/reviews?vendor_id=3&limit=20&offset=0
```

Each returned review includes its user, vendor, rating, optional comment,
creation time, and image metadata. The list response also includes `total`,
`limit`, and `offset` so the frontend can build pagination controls.

### Delete a review

`DELETE /reviews/{review_id}` requires the temporary user header. A normal user
may delete only their own review; an administrator may delete any review.

```powershell
Invoke-RestMethod `
    -Method Delete `
    -Uri http://127.0.0.1:8000/reviews/1 `
    -Headers @{ "X-Dev-User-Id" = "4" }
```

A successful deletion returns HTTP `204` with an empty body. The API returns
`403` when another normal user owns the review and `404` when the review does
not exist. Related `review_images` database records are removed automatically.
Deleting external image files will be added when the storage provider is
selected.

### List food stalls

`GET /vendors` is public and gives the frontend the available food stalls and
their IDs:

```text
http://127.0.0.1:8000/vendors
```

It supports:

| Query parameter | Default | Purpose |
| --- | ---: | --- |
| `q` | none | Search name, location, or category |
| `limit` | `100` | Number of food stalls to return; maximum `100` |
| `offset` | `0` | Number of food stalls to skip for pagination |

Each item contains the vendor fields, `review_count`, and `average_rating`.
The average is calculated from current reviews and is `null` when a food stall
has no reviews.

Run the schema and database integration tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Stop the local services without deleting database data:

```powershell
docker compose stop
```

Use `docker compose down` to remove the container and network. The named
database volume is retained unless `--volumes` is explicitly supplied.
