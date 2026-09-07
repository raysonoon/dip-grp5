# Database schema reference

The database tables are modelled as SQLAlchemy ORM classes in
[`apps/api/app/models/`](../apps/api/app/models/). Each file below maps to one or
more tables.

| Table | Model file | Purpose |
| --- | --- | --- |
| `users` | `user.py` | Registered app users |
| `vendors` | `vendor.py` | Food stalls / vendors |
| `vendor_images` | `vendor.py` | Ordered images for a vendor |
| `reviews` | `review.py` | Community reviews written by users |
| `review_images` | `review.py` | Ordered images attached to a review |
| `google_reviews` | `google_review.py` | Imported Google reviews for a vendor |
| `chatbot_prompts` | `chatbot_prompt.py` | Curated chatbot questions / prompt templates |
| `knowledge_chunks` | `knowledge.py` | Text chunks with pgvector embeddings (RAG) |

Most tables use the shared declarative `Base` from
[`app/db/base.py`](../apps/api/app/db/base.py). The `knowledge_chunks` table uses
the separate `VectorBase` from [`app/db/vector_base.py`](../apps/api/app/db/vector_base.py)
so the pgvector extension can be enabled independently.

## `users`

Community members who write reviews and log into the app.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `display_name` | varchar(100) | no | |
| `email_address` | varchar(320) | no | Preserved for display and delivery |
| `email_canonical` | varchar(320) | no | `lower(trim(email_address))`, unique |
| `password_hash` | varchar(255) | no | Argon2 hash |
| `role` | varchar(20) | no | `user` or `admin` (default `user`) |
| `affiliation` | varchar(100) | yes | Optional profile field |
| `created_at` | timestamptz | no | Defaults to `now()` |

Constraints / indexes:

- `role_allowed`: `role IN ('user', 'admin')`
- `email_canonical_matches_address`: `email_canonical = lower(trim(email_address))`
- `uq_users_email_canonical`: unique index on `email_canonical`

## `vendors`

Food stalls displayed to users.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `directory_id` | varchar(10) | yes | Unique external directory id |
| `name` | varchar(200) | no | |
| `location` | varchar(255) | yes | |
| `category` | varchar(100) | yes | |
| `opening_hours` | varchar(255) | yes | |
| `average_google_rating` | numeric(2,1) | yes | `0` to `5` |
| `created_at` | timestamptz | no | Defaults to `now()` |
| `updated_at` | timestamptz | no | Defaults to `now()`, updates on change |

Constraints / indexes:

- `uq_vendors_directory_id`: unique on `directory_id`
- `average_google_rating_range`: `average_google_rating IS NULL OR average_google_rating BETWEEN 0 AND 5`

## `vendor_images`

Ordered image metadata for a vendor.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `vendor_id` | integer (FK `vendors.id`) | no | On delete `CASCADE` |
| `image_url` | text | no | URL only, no binary upload |
| `display_order` | smallint | no | Ordering; first image is the thumbnail |
| `created_at` | timestamptz | no | Defaults to `now()` |

Constraints / indexes:

- `display_order_positive`: `display_order >= 1`
- `uq_vendor_images_vendor_display_order`: unique on (`vendor_id`, `display_order`)
- `ix_vendor_images_vendor_id`: index on `vendor_id`

## `reviews`

Community reviews of vendors written by users.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `user_id` | integer (FK `users.id`) | no | On delete `RESTRICT` |
| `vendor_id` | integer (FK `vendors.id`) | no | On delete `RESTRICT` |
| `rating_half_steps` | smallint | no | `2` to `10` (maps to 1.0–5.0 in 0.5 steps) |
| `comment` | text | yes | Whitespace-only stored as `NULL` |
| `created_at` | timestamptz | no | Defaults to `now()` |
| `updated_at` | timestamptz | yes | Set when edited |

Constraints / indexes:

- `rating_half_steps_range`: `rating_half_steps BETWEEN 2 AND 10`
- `ix_reviews_user_id`: index on `user_id`
- `ix_reviews_vendor_created_at`: index on (`vendor_id`, `created_at`)

## `review_images`

Ordered image metadata attached to a review.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `review_id` | integer (FK `reviews.id`) | no | On delete `CASCADE` |
| `image_url` | text | no | URL only, no binary upload |
| `mime_type` | varchar(20) | no | `image/jpeg` or `image/png` |
| `file_size_bytes` | integer | no | `1` to `5242880` (5 MB) |
| `display_order` | smallint | no | `1` to `5` |
| `created_at` | timestamptz | no | Defaults to `now()` |

Constraints / indexes:

- `mime_type_allowed`: `mime_type IN ('image/jpeg', 'image/png')`
- `file_size_bytes_range`: `file_size_bytes BETWEEN 1 AND 5242880`
- `display_order_range`: `display_order BETWEEN 1 AND 5`
- `uq_review_images_review_display_order`: unique on (`review_id`, `display_order`)
- `ix_review_images_review_id`: index on `review_id`

## `google_reviews`

Reviews imported from Google for a vendor.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `vendor_id` | integer (FK `vendors.id`) | no | On delete `RESTRICT` |
| `external_review_id` | varchar(255) | no | Unique external id |
| `rating` | smallint | no | `1` to `5` |
| `comment` | text | yes | |
| `published_at` | timestamptz | no | |

Constraints / indexes:

- `rating_range`: `rating BETWEEN 1 AND 5`

## `chatbot_prompts`

Curated chatbot questions and prompt templates.

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `intent_key` | varchar(100) | no | Unique, normalized to lowercase |
| `question_scope` | text | no | |
| `question_text` | text | yes | |
| `search_type` | varchar(20) | yes | `SQL`, `Vector`, or `SQL + Vector` |
| `source_file` | varchar(255) | yes | Source workbook filename |
| `prompt_template` | text | yes | Nullable until prompt authoring begins |
| `is_active` | boolean | no | Default `true` |
| `created_at` | timestamptz | no | Defaults to `now()` |
| `updated_at` | timestamptz | no | Defaults to `now()`, updates on change |

Constraints / indexes:

- `intent_key_not_blank`: `length(trim(intent_key)) > 0`
- `question_scope_not_blank`: `length(trim(question_scope)) > 0`
- `prompt_template_not_blank`: `prompt_template IS NULL OR length(trim(prompt_template)) > 0`
- `question_text_not_blank`: `question_text IS NULL OR length(trim(question_text)) > 0`
- `search_type_allowed`: `search_type IS NULL OR search_type IN ('SQL', 'Vector', 'SQL + Vector')`
- `source_file_not_blank`: `source_file IS NULL OR length(trim(source_file)) > 0`
- `question_has_search_type`: `question_text IS NULL OR search_type IS NOT NULL`
- `question_or_prompt_present`: `question_text IS NOT NULL OR prompt_template IS NOT NULL`

## `knowledge_chunks`

Retrievable text chunks with pgvector embeddings for chatbot RAG. Uses the
separate `VectorBase`. Embedding dimensions come from
`settings.embedding_dimensions` (default `768`).

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | integer (identity PK) | no | |
| `source_type` | varchar(32) | no | `internal_review`, `reddit`, or `google_review` |
| `source_id` | varchar(255) | yes | Id of the source record |
| `vendor_id` | integer | yes | |
| `content` | text | no | |
| `embedding` | vector(768) | no | pgvector embedding |
| `metadata` | json | yes | Extra metadata |
| `created_at` | timestamptz | no | Defaults to `now()` |
| `updated_at` | timestamptz | no | Defaults to `now()`, updates on change |

Constraints / indexes:

- `source_type_allowed`: `source_type IN ('internal_review', 'reddit', 'google_review')`
- `content_not_blank`: `length(trim(content)) > 0`
- `ix_knowledge_chunks_embedding_hnsw`: HNSW index on `embedding` using
  `vector_cosine_ops` (`m = 16`, `ef_construction = 64`)
