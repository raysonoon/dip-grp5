"""One-off script to backfill vendor map_coordinates for existing rows."""
from geoalchemy2.functions import ST_GeogFromText

from app.db.session import SessionLocal
from app.models import Vendor

# vendor_id -> (lat, lng)
# Approximate cluster points per building/area, not verified per vendor.
VENDOR_COORDINATES: dict[int, tuple[float, float]] = {
    3: (1.3477, 103.6800), 8: (1.3477, 103.6800), 9: (1.3477, 103.6800),
    11: (1.3477, 103.6800), 12: (1.3477, 103.6800), 13: (1.3477, 103.6800),
    18: (1.3477, 103.6800), 28: (1.3477, 103.6800), 36: (1.3477, 103.6800),
    40: (1.3477, 103.6800), 41: (1.3477, 103.6800), 45: (1.3477, 103.6800),
    50: (1.3477, 103.6800), 51: (1.3477, 103.6800), 53: (1.3477, 103.6800),
    55: (1.3477, 103.6800), 58: (1.3477, 103.6800),
    5: (1.3481, 103.6796), 10: (1.3481, 103.6796), 19: (1.3481, 103.6796),
    35: (1.3481, 103.6796), 39: (1.3481, 103.6796), 42: (1.3481, 103.6796),
    44: (1.3481, 103.6796), 48: (1.3481, 103.6796), 49: (1.3481, 103.6796),
    57: (1.3481, 103.6796),
    15: (1.3466, 103.6822), 31: (1.3466, 103.6822), 33: (1.3466, 103.6822),
    47: (1.3466, 103.6822), 34: (1.3466, 103.6822), 52: (1.3466, 103.6822),
    56: (1.3466, 103.6822),
    4: (1.3502, 103.6875), 6: (1.3502, 103.6875), 29: (1.3502, 103.6875),
    38: (1.3502, 103.6875), 37: (1.3502, 103.6875),
    17: (1.3454, 103.6785), 16: (1.3454, 103.6785),
    20: (1.3445, 103.6845), 24: (1.3448, 103.6848), 25: (1.3450, 103.6850),
    21: (1.3440, 103.6790), 22: (1.3505, 103.6870), 23: (1.3510, 103.6880),
    7: (1.3505, 103.6870),
    26: (1.3435, 103.6795), 43: (1.3470, 103.6910),
    27: (1.3500, 103.6790),
    1: (1.3483, 103.6831), 2: (1.3483, 103.6831), 54: (1.3483, 103.6831),
    14: (1.3460, 103.6815), 30: (1.3452, 103.6783), 32: (1.3460, 103.6810),
    46: (1.3410, 103.6800),
}


def run() -> None:
    session = SessionLocal()
    try:
        updated = 0
        for vendor_id, (lat, lng) in VENDOR_COORDINATES.items():
            vendor = session.get(Vendor, vendor_id)
            if vendor is None:
                continue
            # WKT points are (longitude latitude), the reverse of the tuple above.
            vendor.map_coordinates = ST_GeogFromText(f"POINT({lng} {lat})")
            updated += 1
        session.commit()
        print(f"Backfilled coordinates for {updated} vendors.")
    finally:
        session.close()


if __name__ == "__main__":
    run()