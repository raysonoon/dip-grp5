# dip-grp5

NTU Foodie Hub — a campus food discovery app with community reviews and a
RAG chatbot. The repo has a FastAPI backend (`apps/api`) and a React SPA
frontend (`apps/web`).

## Folder structure

```text
dip-grp5/
├── README.md
├── AGENTS.md                      # Agent/assistant instructions for this repo
├── start-fastapi.bat              # One-click backend launcher (Docker, DB, migrations, API)
├── start-fastapi.sh               # Same launcher for macOS/Linux
├── data/                          # Source data + scraping scripts used for seeding
│   ├── fnb-directory-v2.csv
│   ├── knowledge_chunks.csv       # Committed RAG knowledge-base export
│   ├── google_reviews/
│   ├── reddit/
│   └── vendor_photos/
├── diagrams/                      # Architecture and flow diagrams
│   ├── dip_architecture_220826.jpg
│   ├── chatbot_rag.jpg
│   └── chatbot_routing.jpg
├── docs/                          # Working documents and design notes
│   ├── chatbot.md                 # Chatbot RAG vector-search design notes
│   ├── db-schema.md               # Database tables reference
│   ├── devops.md                  # Deployment notes (Cloudflare / Cloud Run / Supabase)
│   ├── DIP AI chatbot questions.xlsx
│   ├── DIP Chatbot Schema.xlsx
│   ├── DIP_AI_chatbot_questions_v2.xlsx
│   ├── week-3.md ... week-9.md
│   ├── TODO.md
│   └── Still NEED.txt
└── apps/
    ├── api/                       # FastAPI backend
    │   ├── app/
    │   │   ├── main.py            # App entrypoint + router registration
    │   │   ├── api/
    │   │   │   ├── dependencies.py # Auth + DB session dependencies
    │   │   │   └── routes/
    │   │   │       ├── auth.py    # GET /auth/me, /auth/me/reviews
    │   │   │       ├── chat.py    # POST /chat/stream (RAG chatbot, SSE)
    │   │   │       ├── preferences.py # Food-preferences endpoints
    │   │   │       ├── reviews.py
    │   │   │       └── vendors.py
    │   │   ├── core/
    │   │   │   ├── config.py      # Pydantic settings (env vars)
    │   │   │   ├── image_storage.py
    │   │   │   ├── image_upload.py
    │   │   │   └── security.py    # Argon2 hashing + Supabase JWT verification
    │   │   ├── db/
    │   │   │   ├── base.py        # Shared declarative Base + naming convention
    │   │   │   ├── vector_base.py # Separate Base for pgvector tables
    │   │   │   ├── chatbot_question_data.py  # Curated question rows
    │   │   │   ├── reindex.py     # (Re)build the pgvector index
    │   │   │   ├── seed.py        # Repeatable dev seed
    │   │   │   ├── seed_reddit.py
    │   │   │   ├── seed_vendor_images.py
    │   │   │   └── session.py     # Engine + session factory
    │   │   ├── models/            # SQLAlchemy ORM (database tables)
    │   │   ├── schemas/           # Pydantic API request/response DTOs
    │   │   └── services/          # Chatbot / RAG pipeline
    │   │       ├── chat.py
    │   │       ├── chunking.py
    │   │       ├── embedding.py
    │   │       ├── ingest.py
    │   │       ├── intent_router.py
    │   │       ├── llm_routing.py
    │   │       ├── retrieval.py
    │   │       ├── review_knowledge.py
    │   │       ├── sql_search.py
    │   │       ├── structured_filters.py
    │   │       ├── vendor_matching.py
    │   │       └── vendor_search.py
    │   ├── alembic/               # Database migrations
    │   │   └── versions/
    │   ├── tests/                 # Pytest suite (incl. vector integration tests)
    │   ├── uploads/               # Local image files (vendor/review images)
    │   ├── alembic.ini
    │   ├── compose.yaml           # Local Postgres (pgvector) container
    │   ├── Dockerfile.postgres    # Postgres image with pgvector/PostGIS extensions
    │   ├── pytest.ini
    │   ├── requirements.txt
    │   └── .env.example
    └── web/                       # Vite + React SPA frontend (mixed JS/TS)
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
            ├── App.tsx            # Routes + home page
            ├── index.css          # Imports the styles/ files
            ├── api/               # Fetch API clients + tests
            ├── components/        # Shared UI (Layout, Header, chat, map)
            ├── contexts/          # AuthContext
            ├── features/          # Domain feature modules (reviews, vendors)
            ├── hooks/             # useChatSession
            ├── lib/               # Shared helpers (auth, supabase, maps)
            ├── pages/             # FoodPage, VendorsPage, MapPage, SignInPage, NotFoundPage
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

The seed also imports `data/knowledge_chunks.csv` (committed with the repo) to
populate the chatbot RAG knowledge base. This is skipped automatically once the
table already has rows, so it only runs on a fresh database. To regenerate the
CSV from a populated database, export the shareable chunks (Google + Reddit,
excluding per-database `internal_review` rows):

```powershell
docker exec dip-grp5-postgres psql -U postgres -d dip_grp5 -c "\copy (SELECT source_type, source_id, content, embedding, metadata FROM knowledge_chunks WHERE source_type <> 'internal_review') to '/tmp/knowledge_chunks.csv' with (format csv, header)"
docker cp dip-grp5-postgres:/tmp/knowledge_chunks.csv data/knowledge_chunks.csv
```

`vendor_id` is resolved at import time from the already-seeded Google/Reddit
tables, so the CSV stays correct even if local vendor IDs differ. To rebuild the
knowledge base from the source data instead (requires `GEMINI_API_KEY`), run
`python -m app.db.reindex`.

Alternatively, run the one-click launcher at the repo root, which checks Docker,
starts PostgreSQL, applies migrations, seeds development data, and opens the API
documentation:

```powershell
.\start-fastapi.bat
```

macOS/Linux users run the equivalent bash launcher instead:

```bash
./start-fastapi.sh
```

Both do the same thing (Docker + migrations + seed + `fastapi dev`); the `.sh`
script runs FastAPI in the foreground. Prerequisites are identical: Docker
Desktop and the `apps/api/.venv` environment.

### Run the API

Start FastAPI from `apps/api` (venv active):

```powershell
python -m fastapi dev app/main.py
```

Open <http://127.0.0.1:8000/docs> to use the interactive API page.

### Authentication

Protected API actions require a signed-in Supabase session. The backend
verifies the Supabase bearer token and creates or links the corresponding local
user profile when the frontend calls `/auth/me`.

## Local frontend environment

### First-time setup

```powershell
Set-Location apps\web
npm install
Copy-Item .env.example .env
```

Sign in through Supabase before using authenticated actions such as creating,
editing, or deleting reviews. Interacting with chatbot and browsing public vendors and reviews does not
require a session.

### Run the frontend

Start the Vite dev server:

```powershell
npm run dev
```

Open <http://127.0.0.1:5173> in a browser. The Vite server proxies `/auth`,
`/preferences`, `/chat`, `/reviews`, `/vendors`, and `/media` to the FastAPI
backend on port `8000`, so start the API first (see above).

### Frontend checks

```powershell
npm test          # Node test runner (API clients, citation markers, vendor ranking)
npm run lint:fix  # ESLint with auto-fix (the only lint script defined)
npm run build     # Production build (vite build; does not typecheck)
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
    -Headers @{ Authorization = "Bearer <supabase-access-token>" } `
    -ContentType "application/json" `
    -Body $body
```

The API takes `user_id` from the authenticated Supabase token; it does not accept
`user_id` in the request body. An omitted or whitespace-only comment is stored
as `NULL`, so rating-only reviews are supported.

### Read reviews

Reading community reviews is public and does not require authentication:

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

### Read your own reviews

`GET /auth/me/reviews` requires a Supabase bearer token and returns the signed-in
user's reviews, newest first. It is used by the Account page.

| Query parameter | Default | Purpose |
| --- | ---: | --- |
| `limit` | `10` | Number of reviews to return; maximum `100` |
| `offset` | `0` | Number of reviews to skip for pagination |

Each item includes the review `id`, `rating`, optional `comment`, `created_at`,
and its `vendor` (`id`, `name`). The response also includes `total`, `limit`,
and `offset`. `GET /auth/me` returns only the profile (`id`, `display_name`,
`role`).

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
    -Headers @{ Authorization = "Bearer <supabase-access-token>" } `
    -ContentType "application/json" `
    -Body $body
```

### Delete a review

`DELETE /reviews/{review_id}` requires a Supabase bearer token. A normal user
may delete only their own review; an administrator may delete any review.

```powershell
Invoke-RestMethod `
    -Method Delete `
    -Uri http://127.0.0.1:8000/reviews/1 `
    -Headers @{ Authorization = "Bearer <supabase-access-token>" }
```

A successful deletion returns HTTP `204` with an empty body. The API returns
`403` when another normal user owns the review and `404` when the review does
not exist. Related `review_images` database records are removed automatically.
Deleting external image files will be added when the storage provider is
selected.

### Vote on a review

`POST /reviews/{review_id}/vote` requires a Supabase bearer token. The body is
`{ "vote": "up" }` or `{ "vote": "down" }`. Voting the same value again removes
the vote; voting the opposite value switches it. The response returns
`upvote_count`, `downvote_count`, and `current_user_vote`.

### List food stalls

`GET /vendors` is public and gives the frontend the available food stalls and
their IDs:

```text
http://127.0.0.1:8000/vendors
```

It supports:

| Query parameter | Default | Purpose |
| --- | ---: | --- |
| `q` | none | Free-text search across name, category, location, unit code, and dishes |
| `location` | none | Filter by location (substring match; `Hall ...` is matched exactly) |
| `category` | none | Filter by exact category |
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

Geospatial and filter-helper endpoints used by the map and food pages:

```text
GET /vendors/nearby    # lat, lng, max_distance_m, min_rating, limit
GET /vendors/filters   # distinct locations and categories
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
administrator authenticated through Supabase.
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

### Favourites

Signed-in users can save vendors from their detail page and find them in
Account → Favourite places (five per page, newest first). Guests see a
sign-in/sign-up prompt. Apply the new `d103f25a0001` migration with
`python -m alembic upgrade head` from `apps/api` before using this feature.

All endpoints use the authenticated user's identity:

```text
GET    /auth/me/favourites?limit=5&offset=0
GET    /auth/me/favourites/{vendor_id}
PUT    /auth/me/favourites/{vendor_id}
DELETE /auth/me/favourites/{vendor_id}
```

`PUT` creates or refreshes a favourite, moving it to the top without duplicate
rows. `DELETE` is safe to repeat and removes only the caller's favourite.

### Chatbot

`POST /chat/stream` is public and streams the RAG chatbot answer as
server-sent events. It accepts a body of `{ "question": "..." }` (plus optional
chat history) and an optional Supabase bearer token for personalization. It
requires `GEMINI_API_KEY`. See [Chatbot RAG design](docs/chatbot.md) for the
routing paths (`SQL`, `Vector`, `SQL + Vector`) and the ingestion flow.

The `chatbot_prompts` table stores the curated example questions and acts as the
router config. Each question has a stable key, its original text, a concise
question scope, a search type (`SQL`, `Vector`, or `SQL + Vector`), source-file
metadata, an `is_active` switch, and timestamps.

The repeatable development seed imports 59 unique questions from
`DIP AI chatbot questions.xlsx` and `DIP Chatbot Schema.xlsx`. One exact question
appears in both files and is stored once with both sources.

## Tests

Run the backend test suite from `apps/api` (venv active). It uses an in-memory
SQLite database and does not need Docker or PostgreSQL running:

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