# Local image uploads

This directory stores image files for local development. PostgreSQL stores the
image metadata and relative URL; it does not store the image binary.

## Directory structure

```text
uploads/
├── README.md
├── vendor_images/
│   ├── .gitkeep
│   └── {vendor_id}/
│       ├── {vendor_image_id}.jpg
│       └── {vendor_image_id}.png
└── review_images/
    ├── .gitkeep
    └── {review_id}/
        ├── .gitkeep
        ├── {review_image_id}.jpg
        └── {review_image_id}.png
```

Example:

```text
uploads/
├── vendor_images/
│   ├── 3/
│   │   ├── 301.jpg
│   │   └── 302.png
│   └── 45/
│       └── 303.jpg
└── review_images/
    ├── 18/
    │   ├── .gitkeep
    │   ├── 801.jpg
    │   └── 802.jpg
    ├── 19/
    │   └── .gitkeep
    ├── 20/
    │   └── .gitkeep
    └── 21/
        └── .gitkeep
```

## Storage rules

- Use the integer primary key of the corresponding image table row as the
  filename: `vendor_images.id` or `review_images.id`.
- Insert and flush the database row first to obtain its integer ID, then save
  the file using that ID. Do not calculate the next ID from existing files.
- Store vendor images under `vendor_images/{vendor_id}/`.
- Store review images under `review_images/{review_id}/`.
- Accept only JPEG and PNG files.
- Store relative URLs in the database, for example:
  - `/media/vendor_images/12/301.jpg`
  - `/media/review_images/101/801.jpg`
- Do not store Windows absolute paths such as `D:\projectS\...` in the
  database.
- Runtime image files are ignored by Git. The `.gitkeep` files preserve the
  empty directory structure.
- Deleting a database image record must also delete its corresponding local
  file; a database cascade does not remove filesystem files.

## Current database directories

The committed placeholder directories mirror the current local database IDs:

- Vendor IDs: `3`, `4`, and `45` through `100`.
- Review IDs: `18`, `19`, `20`, `21`, `86`, `87`, and `88`.

When a new vendor or review is created, its numeric directory should be
created automatically by the upload workflow.
