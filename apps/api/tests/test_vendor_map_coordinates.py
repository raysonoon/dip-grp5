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


def _point(rows: dict[str, dict[str, str]], vendor_id: str) -> tuple[float, float]:
    match = PATTERN.match(rows[vendor_id]["map_coordinates"].strip())
    assert match, vendor_id
    return float(match.group(1)), float(match.group(2))


def test_wee_cho_yaw_plaza_crowded_bowl_is_not_at_north_spine() -> None:
    rows = _rows_by_id()
    north_spine = _point(rows, "V049")
    plaza_bowl = _point(rows, "V050")
    plaza_coffee = _point(rows, "V054")
    assert plaza_bowl != north_spine
    assert abs(plaza_bowl[0] - plaza_coffee[0]) < 0.002
    assert abs(plaza_bowl[1] - plaza_coffee[1]) < 0.002


def test_hill_yard_is_in_the_north_hill_halls_block() -> None:
    rows = _rows_by_id()
    hill_yard = _point(rows, "V027")
    a_hot_hideout = _point(rows, "V002")
    assert abs(hill_yard[0] - a_hot_hideout[0]) < 0.003
    assert abs(hill_yard[1] - a_hot_hideout[1]) < 0.003