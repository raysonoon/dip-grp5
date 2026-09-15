# dip-grp5

NTU Foodie Hub — a campus food discovery app with community reviews and a
RAG chatbot. The repo has a FastAPI backend (`apps/api`) and a React SPA
frontend (`apps/web`).

## Folder structure

```text
dip-grp5/
├── README.md
├── start-fastapi.bat              # One-click backend launcher (Docker, DB, migrations, API)
├── data/                          # Source data used for seeding
│   ├── fnb-directory-v2.csv
│   └── google_reviews/
├── diagrams/                      # Architecture and flow diagrams
│   ├── dip_architecture_220826.jpg
│   ├── chatbot_rag.jpg
│   └── chatbot_routing.jpg
├── docs/                          # Working documents and design notes
│   ├── DIP AI chatbot questions.xlsx
│   ├── DIP Chatbot Schema.xlsx
│   ├── db-schema.md               # Database tables reference
│   ├── chatbot.md                 # Chatbot RAG vector-search design notes
│   ├── week-3.md
│   ├── week-4.md
│   ├── What Baihao Did wk 3.md
│   ├── TODO.md
│   └── Still NEED.txt
└── apps/
    ├── api/                       # FastAPI backend
    │   ├── app/
    │   │   ├── main.py            # App entrypoint + router registration
    │   │   ├── api/
    │   │   │   ├── dependencies.py # Dev auth + DB session dependencies
    │   │   │   └── routes/
    │   │   │       ├── chat.py    # POST /chat (RAG chatbot)
    │   │   │       ├── reviews.py
    │   │   │       └── vendors.py
    │   │   ├── core/
    │   │   │   ├── config.py      # Pydantic settings (env vars)
    │   │   │   ├── image_storage.py
    │   │   │   ├── image_upload.py
    │   │   │   └── security.py    # Argon2 password hashing
    │   │   ├── db/
    │   │   │   ├── base.py        # Shared declarative Base + naming convention
    │   │   │   ├── vector_base.py # Separate Base for pgvector tables
    │   │   │   ├── chatbot_question_data.py  # Curated question rows
    │   │   │   ├── reindex.py     # (Re)build the pgvector index
    │   │   │   ├── seed.py        # Repeatable dev seed
    │   │   │   └── session.py     # Engine + session factory
    │   │   ├── models/            # SQLAlchemy ORM (database tables)
    │   │   ├── schemas/           # Pydantic API request/response DTOs
    │   │   └── services/          # Chatbot / RAG pipeline
    │   │       ├── chat.py
    │   │       ├── chunking.py
    │   │       ├── embedding.py
    │   │       ├── ingest.py
    │   │       ├── retrieval.py
    │   │       └── review_knowledge.py
    │   ├── alembic/               # Database migrations
    │   │   └── versions/
    │   ├── docker/
    │   │   └── init/
    │   │       └── 01-enable-vector.sql  # Enables the pgvector extension
    │   ├── tests/                 # Pytest suite (incl. vector integration tests)
    │   ├── uploads/               # Local image files (vendor/review images)
    │   ├── alembic.ini
    │   ├── compose.yaml           # Local Postgres (pgvector) container
    │   ├── pytest.ini
    │   ├── requirements.txt
    │   └── .env.example
    └── web/                       # Vite + React (TS) SPA frontend
        ├── index.html
        ├── package.json           # App dependencies + scripts
        ├── eslint.config.js
        ├── tsconfig.json
        ├── tsconfig.node.json
        ├── vite.config.ts         # Dev proxy to the FastAPI backend
        ├── public/
        │   └── favicon.svg
        └── src/
            ├── main.tsx
            ├── App.tsx            # Routes + home page + chat widget
            ├── index.css          # Imports the styles/ files
            ├── api/               # Fetch API clients + tests
            ├── data/              # Local fallback vendor data
            ├── features/          # Domain feature modules
            ├── lib/               # Shared helpers
            ├── pages/             # FoodPage, VendorsPage
            ├── styles/            # fonts, tailwind, theme
            └── types/             # Frontend TypeScript interfaces
```

## Architecture

![software architecture](diagrams/dip_architecture_220826.jpg)

## Project documentation

- [Database schema reference](docs/db-schema.md)

## Prerequisites

- **Python 3.12** for the backend
- **Docker Desktop** for the local PostgreSQL (pgvector) database
- **Node.js 18+** and **npm** for the frontend

## Local backend environment

### First-time setup

```powershell
Set-Location apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Change the local-only database password in `.env`, then start PostgreSQL with
the pgvector extension:

```powershell
docker compose up -d
docker compose ps
```

Create or update the database tables, then seed with local placeholder data:

```powershell
python -m alembic upgrade head
python -m app.db.seed
```

The repeatable seed command creates or confirms these local placeholders:

| Type | Display name / email | Password/role |
| --- | --- | --- |
| Administrator | `Administrator` / `admin@local.invalid` | password `admin`, role `admin` |
| Normal user | `Test User` / `test-user@local.invalid` | password `test`, role `user` |
| Food stall | `Demo Vendor 1` | `Demo Canteen` |
| Food stall | `Demo Vendor 2` | `Demo Canteen` |

Passwords are stored as Argon2 hashes. Running the seed command again does not
create duplicate placeholders. Its output shows the generated IDs.
Email addresses are trimmed and preserved for display and delivery. A separate
lowercase canonical value enforces uniqueness without regard to case. Display
names are not unique and may be shared by multiple users.
The optional `affiliation` field is retained as part of the user profile and is
included with the public review-author summary.

Alternatively, run the one-click launcher at the repo root, which checks Docker,
starts PostgreSQL, applies migrations, seeds development data, and opens the API
documentation:

```powershell
.\start-fastapi.bat
```

### Run the API

Start FastAPI from `apps/api` (venv active):

```powershell
python -m fastapi dev app/main.py
```

Open <http://127.0.0.1:8000/docs> to use the interactive API page.

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

## Local frontend environment

### First-time setup

```powershell
Set-Location apps\web
npm install
Copy-Item .env.example .env
```

Set `VITE_DEV_USER_ID` in `apps/web/.env` to a seeded user ID from the backend
seed output (see [Local backend environment](#local-backend-environment)). The
frontend sends it as the `X-Dev-User-Id` header for authenticated actions such
as creating, editing, or deleting reviews. Leave it empty to browse only.

On a fresh database seed, the user IDs are assigned in creation order:

| `VITE_DEV_USER_ID` | User |
| --- | --- |
| `1` | Administrator |
| `2` | Test User |

These are auto-generated `Identity` IDs, so they may differ if rows were added
or removed previously. Always confirm against the IDs printed by
`python -m app.db.seed`. The Test User (`2`) authors the seeded demo reviews, so
it is the usual choice for exercising review add/edit/delete in the UI.

### Run the frontend

Start the Vite dev server:

```powershell
npm run dev
```

Open <http://127.0.0.1:5173> in a browser. The Vite server proxies `/chat`,
`/reviews`, `/vendors`, and `/media` to the FastAPI backend on port `8000`, so
start the API first (see above).

### Frontend checks

```powershell
npm test        # Node test runner for the API clients
npm run lint    # ESLint
npm run build   # Production build
```

## API reference

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
creation time, optional `updated_at`, `is_edited`, and image metadata. Public
user data exposes `display_name`, not the email address. The list response also
includes `total`, `limit`, and `offset` so the frontend can build pagination.

### Edit a review

`PATCH /reviews/{review_id}` allows the review author to change the rating,
comment, or both. The API rejects edits by other users. A successful edit sets
`updated_at` and returns `is_edited: true`, which the frontend can render as
`(edited)`.

```powershell
$body = @{
    rating = 4.5
    comment = "Updated review"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Patch `
    -Uri http://127.0.0.1:8000/reviews/1 `
    -Headers @{ "X-Dev-User-Id" = "1" } `
    -ContentType "application/json" `
    -Body $body
```

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

Vendor images are stored in the separate `vendor_images` table. Each item
contains an ordered `images` list and retains a derived `image_url` containing
the first image for frontend compatibility. Items also contain `updated_at`,
`review_count`, and `average_rating`. The stored average is calculated from
internal reviews and is `null` when a food stall has no internal reviews. A
database trigger keeps it synchronized when internal reviews change.

The vendor schema uses `unit_code` for the stall unit. Google-enriched data is
merged into the standard vendor fields; `average_google_rating` is the only
Google-specific vendor field returned by the API.

The stored internal average can also be read independently from Google ratings:

```text
GET /vendors/{vendor_id}/average-rating
```

Vendor image metadata can be managed through these endpoints:

```text
GET    /vendors/{vendor_id}/images
GET    /vendors/{vendor_id}/images/{image_id}
POST   /vendors/{vendor_id}/images
PATCH  /vendors/{vendor_id}/images/{image_id}
DELETE /vendors/{vendor_id}/images/{image_id}
POST   /reviews/{review_id}/images
GET    /reviews/{review_id}/images/{image_id}
PATCH  /reviews/{review_id}/images/{image_id}
DELETE /reviews/{review_id}/images/{image_id}
```

The two item-level `GET` endpoints are public. They load the image record from
the database, resolve its root-relative `/media/...` URL inside the matching
integer vendor/review upload directory, and return the JPEG or PNG file.
Creating, editing, reordering, and deleting vendor image metadata require an
administrator through the temporary development authentication dependency.
`POST` accepts a root-relative `image_url` under the matching
`/media/vendor_images/{vendor_id}/` directory and an optional positive
`display_order`; when the order is omitted, the API appends the image. The first
ordered image is the vendor thumbnail. This API stores image URLs and metadata
only—it does not upload binary image files.

`POST /reviews/{review_id}/images` accepts one multipart form-data field named
`file`. The authenticated review author may upload JPEG or PNG content up to
5 MB; each review supports at most five images. The API detects the actual file
type, creates the database metadata, and saves the file under the matching
`uploads/review_images/{review_id}/` directory.

`PATCH /reviews/{review_id}/images/{image_id}` lets the review author replace
the multipart `file`, change the form field `display_order`, or do both.
`DELETE /reviews/{review_id}/images/{image_id}` removes the database record and
its local file; the review author or an administrator may delete it.

### Chatbot prompt storage

The `chatbot_prompts` table first stores the curated example questions used to
design the chatbot. Each question has a stable key, its original text, a concise
question scope, a search type (`SQL`, `Vector`, or `SQL + Vector`), source-file
metadata, an `is_active` switch, and timestamps. `prompt_template` remains
nullable until prompt authoring begins.

The repeatable development seed imports 59 unique questions from
`DIP AI chatbot questions.xlsx` and `DIP Chatbot Schema.xlsx`. One exact question
appears in both files and is stored once with both sources. Prompt lookup APIs
and the LLM connection are intentionally left for the next chatbot step.

## Tests

Run the backend schema and database integration tests from `apps/api` (venv
active):

```powershell
python -m pytest -q
```

The pgvector integration tests (`test_vector_search.py`) are skipped unless
`TEST_DATABASE_URL` is set. Example:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:change_me@127.0.0.1:5433/dip_grp5"
python -m pytest -q -m vector
```

Run the frontend tests from `apps/web`:

```powershell
npm test
```

## Stop the local services

Stopping the containers without deleting database data:

```powershell
docker compose stop
```

Use `docker compose down` to remove the container and network. The named
database volume is retained unless `--volumes` is explicitly supplied.