# What Baihao Did — Week 3

- Replaced `username` with a non-unique `display_name`.
- Added unique email addresses with case-insensitive comparison.
- Kept `affiliation` as an optional user field.
- Added review update timestamps and an `(edited)` status.
- Allowed users to edit their own reviews.
- Created the `vendor_images` database table.
- Implemented APIs to view, add, update, and delete vendor image URLs.
- Restricted vendor image changes to administrators.
- Created the Chatbot database table.
- Organized and imported 59 Chatbot questions from two Excel files.
- Updated and synchronized the PostgreSQL database structure using Alembic migrations.
- Applied the database changes to the local Docker PostgreSQL instance.
- Added backend automated tests, with `18 passed`.
- Updated the backend README and TODO.
