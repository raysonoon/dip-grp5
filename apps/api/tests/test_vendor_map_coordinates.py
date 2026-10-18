import csv
import re
from pathlib import Path

import pytest

CSV_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "google_reviews"
    / "ntu_food_places_final.csv"
)
VENDOR_IDS = ["V030", "V031", "V052", "V054", "V055"]
PATTERN = re.compile(r"^\(\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*\)$")


def _rows_by_id() -> dict[str, dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        return {row["ID"].strip(): row for row in csv.DictReader(handle)}


@pytest.mark.parametrize("vendor_id", VENDOR_IDS)
def test_vendor_has_map_coordinates_inside_ntu(vendor_id: str) -> None:
    value = _rows_by_id()[vendor_id]["map_coordinates"].strip()
    match = PATTERN.match(value)
    assert match, f"{vendor_id} has bad map_coordinates: {value!r}"
    lat, lng = (float(part) for part in match.groups())
    assert 1.34 <= lat <= 1.36
    assert 103.67 <= lng <= 103.69