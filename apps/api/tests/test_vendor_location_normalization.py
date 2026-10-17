import pytest

from app.db.seed import _normalize_location


@pytest.mark.parametrize(
    "raw",
    ["Tamarind Hall", "Saraca Hall", "Hall 8", "saraca hall ", "HALL  8"],
)
def test_nanyang_crescent_aliases(raw):
    assert _normalize_location(raw) == "Nanyang Crescent"


@pytest.mark.parametrize(
    "raw",
    ["Tanjong", "Tanjong Hall", "Binjai", "Binjai Hall", "Banyan Hall"],
)
def test_north_hill_aliases(raw):
    assert _normalize_location(raw) == "North Hill"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("North Spine", "North Spine"), ("Hall 1 ", "Hall 1"), (None, None)],
)
def test_other_locations_unchanged(raw, expected):
    assert _normalize_location(raw) == expected