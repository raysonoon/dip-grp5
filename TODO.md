# TODO
- [ ] Map
  - markers pinpointing different food stalls
  - clicking marker opens a popup
  - popup shows options more and directions
  - clicking more redirects to vendor information page with community reviews
  - clicking direcitons prompt user to open google maps
- [ ] Chatbot
- [ ] Community reviews
- [ ] Sequence/flow diagrams

## 26/8/26
- Settle database schema
  - [ ] users table
    - [ ] sign in with email? username/email?
    - [ ] use display_name instead of username?
    - [ ] is affiliation necessary?
  - [ ] vendors table
    - [ ] one thumbnail per stall or multi-image gallery
    - [ ] follow kai schema + image_url + created_at
      - [ ] rename last_updated to updated_at
  - [ ] reviews table
    - [ ] updated_at
    - [ ] to allow user to edit their reviews? or delete and create new one?
  - [ ] review_images table
    - [ ] limit to 5?
- Refactor backend into repo 
- Setup backend
  - [ ] Download docker
  - [ ] Download postgresql
  - [ ] env variables
  - [ ] test API
- Finalise UI/UX
  - Community review
    - Omit name field? Get display name from user db
  - To add menu info in stall/vendor page?
    - Or just pictures, like a gallery
- Setup frontend

### folder structure
ntu-foodie-hub/
├── package.json                       # npm workspaces + orchestration scripts
├── package-lock.json
├── docker-compose.yml                 # root: postgres (pgvector) on 127.0.0.1:5433
├── .env.example                       # POSTGRES_DB/USER/PASSWORD for compose
├── .gitignore                         # node_modules, .venv, .env, dist, __pycache__, ...
├── README.md                          # monorepo overview + quickstart

- v1
├── apps/
│   ├── api/                           # FastAPI backend (moved, unchanged)
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
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/
│   │   ├── alembic.ini
│   │   ├── tests/
│   │   │   ├── test_create_review_api.py
│   │   │   ├── test_database_integration.py
│   │   │   ├── test_dev_auth.py
│   │   │   ├── test_model_metadata.py
│   │   │   └── test_vendor_api.py
│   │   ├── docker/
│   │   │   └── init/
│   │   │       └── 01-enable-vector.sql
│   │   ├── docs/
│   │   │   ├── community-review-database-design.md
│   │   │   ├── community-review-erd.svg
│   │   │   ├── community-review-erd.png
│   │   │   └── tables/README.md
│   │   ├── Manual.md
│   │   ├── requirements.txt
│   │   ├── pytest.ini
│   │   ├── .env.example
│   │   └── .env                          # gitignored
│   │
│   └── web/                              # Vite + React (TS) SPA
│       ├── index.html
│       ├── package.json
│       ├── tsconfig.json
│       ├── tsconfig.node.json
│       ├── vite.config.ts                # dev proxy → http://127.0.0.1:8000
│       ├── public/
│       │   └── favicon.svg
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── App.css
│           ├── index.css
│           ├── vite-env.d.ts
│           ├── components/
│           ├── pages/
│           ├── lib/                       # API client helpers
│           └── types/
│
└── packages/                             # empty for now (future shared TS code)

- v2
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