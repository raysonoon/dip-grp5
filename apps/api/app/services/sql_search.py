"""Structured SQL retrieval for the SQL and ``SQL + Vector`` chat paths.

The SQL path queries the relational ``vendors`` / ``reviews`` tables directly,
applying the ``StructuredFilter`` derived from the user's question. The
``SQL + Vector`` path reuses the same filter to resolve the matching
``vendor_id`` set that restricts the vector search.
"""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from app.models import Review, Vendor
from app.services.structured_filters import StructuredFilter

DEFAULT_LIMIT = 20
_PRICE_BANDS = {
    "cheap": ("$", "$$", "$1-10", "$10-20"),
    "expensive": ("$$$", "$$$$", "$20-30"),
}

# Match a range's closing time when it is strictly later than 20:00.  This is
# deliberately expressed as one SQL regular expression instead of enumerating
# minutes, so both ISO times and the dotted am/pm format in the vendor CSV are
# handled.  SQLAlchemy maps ``regexp_match`` to PostgreSQL ``~`` and installs a
# compatible ``REGEXP`` function for SQLite tests.
_OPEN_AFTER_20_REGEX = (
    r"(to|till|until|[-–—]) *("
    r"20[:.](0[1-9]|[1-5][0-9])"
    r"|2[1-3][:.][0-5][0-9]"
    r"|8[:.](0[1-9]|[1-5][0-9]) *p[.]? *m[.]?"
    r"|(9|10|11)([:.][0-5][0-9])? *p[.]? *m[.]?"
    r"|12([:.][0-5][0-9])? *a[.]? *m[.]?"
    r"|midnight"
    r")([^0-9a-z]|$)"
    r"|(^|[^0-9a-z])24([ -]*(hours?|hrs?)|/7|:00)([^0-9a-z]|$)"
)


@dataclass
class SqlResult:
    """A structured row returned by the SQL path."""

    vendor_id: int | None = None
    vendor_name: str | None = None
    location: str | None = None
    unit_code: str | None = None
    address: str | None = None
    category: str | None = None
    cuisine: str | None = None
    price_range: str | None = None
    opening_hours: str | None = None
    halal: bool | None = None
    vegetarian: bool | None = None
    average_rating: float | None = None
    average_google_rating: float | None = None
    review_count: int | None = None
    count: int | None = None


class SqlStore(Protocol):
    """Structured retrieval over the relational vendor tables."""

    def search(self, filters: StructuredFilter) -> list[SqlResult]: ...

    def resolve_vendor_ids(
        self,
        filters: StructuredFilter,
    ) -> list[int]: ...


class PgSqlStore:
    """Apply a ``StructuredFilter`` to ``vendors`` / ``reviews``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, filters: StructuredFilter) -> list[SqlResult]:
        predicates = _build_predicates(filters)

        if filters.query_kind == "count":
            total = self._session.scalar(
                select(func.count(Vendor.id)).where(*predicates)
            )
            return [SqlResult(vendor_id=None, vendor_name=None, count=total or 0)]

        order_by = _build_order_by(filters)
        limit = filters.top_n if filters.query_kind == "rank" else DEFAULT_LIMIT
        rows = self._session.execute(
            select(
                Vendor,
                func.count(Review.id).label("review_count"),
            )
            .outerjoin(Review, Review.vendor_id == Vendor.id)
            .where(*predicates)
            .group_by(Vendor.id)
            .order_by(*order_by)
            .limit(limit)
        ).all()

        return [self._to_result(vendor, review_count) for vendor, review_count in rows]

    def resolve_vendor_ids(self, filters: StructuredFilter) -> list[int]:
        predicates = _build_predicates(filters)
        statement = select(Vendor.id).where(*predicates)
        if filters.top_n is not None:
            statement = statement.limit(filters.top_n)
        return list(self._session.scalars(statement).all())

    @staticmethod
    def _to_result(
        vendor: Vendor,
        review_count: int,
    ) -> SqlResult:
        return SqlResult(
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            location=vendor.location,
            unit_code=vendor.unit_code,
            address=vendor.address,
            category=vendor.category,
            cuisine=vendor.cuisine,
            price_range=vendor.price_range,
            opening_hours=vendor.opening_hours,
            halal=vendor.halal,
            vegetarian=vendor.vegetarian,
            average_rating=(
                None
                if vendor.average_rating is None
                else float(vendor.average_rating)
            ),
            average_google_rating=(
                None
                if vendor.average_google_rating is None
                else float(vendor.average_google_rating)
            ),
            review_count=review_count,
        )


def _build_predicates(filters: StructuredFilter) -> list:
    predicates = []
    if filters.vendor_ids:
        predicates.append(Vendor.id.in_(filters.vendor_ids))
    if filters.halal is not None:
        predicates.append(Vendor.halal.is_(filters.halal))
    if filters.vegetarian is not None:
        predicates.append(Vendor.vegetarian.is_(filters.vegetarian))
    if filters.cuisine:
        pattern = f"%{filters.cuisine}%"
        predicates.append(
            or_(
                Vendor.cuisine.ilike(pattern),
                Vendor.category.ilike(pattern),
                Vendor.dishes.ilike(pattern),
            )
        )
    if filters.exclude_cuisine:
        pattern = f"%{filters.exclude_cuisine}%"
        predicates.append(
            not_(
                or_(
                    func.coalesce(Vendor.cuisine, "").ilike(pattern),
                    func.coalesce(Vendor.category, "").ilike(pattern),
                )
            )
        )
    if filters.location:
        pattern = f"%{filters.location}%"
        predicates.append(
            or_(
                Vendor.location.ilike(pattern),
                Vendor.unit_code.ilike(pattern),
            )
        )
    if filters.exclude_location:
        pattern = f"%{filters.exclude_location}%"
        predicates.append(
            and_(
                not_(func.coalesce(Vendor.location, "").ilike(pattern)),
                not_(func.coalesce(Vendor.unit_code, "").ilike(pattern)),
            )
        )
    if filters.budget in _PRICE_BANDS:
        predicates.append(Vendor.price_range.in_(_PRICE_BANDS[filters.budget]))
    if filters.exclude_budget in _PRICE_BANDS:
        predicates.append(
            or_(
                Vendor.price_range.is_(None),
                not_(
                    Vendor.price_range.in_(
                        _PRICE_BANDS[filters.exclude_budget]
                    )
                ),
            )
        )

    if filters.open_hours:
        open_hours_predicate = _build_open_hours_predicate(filters.open_hours)
        if open_hours_predicate is not None:
            predicates.append(open_hours_predicate)
    if filters.exclude_open_hours:
        open_hours_predicate = _build_open_hours_predicate(
            filters.exclude_open_hours
        )
        if open_hours_predicate is not None:
            predicates.append(not_(open_hours_predicate))
    return predicates


def _build_open_hours_predicate(value: str):
    opening_hours = func.lower(func.coalesce(Vendor.opening_hours, ""))

    if value in {"after 20:00", "late"}:
        return opening_hours.regexp_match(_OPEN_AFTER_20_REGEX)

    if value == "sunday":
        has_sunday_schedule = or_(
            opening_hours.like("%daily%"),
            opening_hours.like("%sunday%"),
            opening_hours.like("%sun:%"),
            opening_hours.like("%sun %"),
            opening_hours.like("%sun&%"),
            opening_hours.like("%sun &%"),
        )
        explicitly_closed = or_(
            opening_hours.like("%sun: closed%"),
            opening_hours.like("%sun - closed%"),
            opening_hours.like("%sun closed%"),
            opening_hours.like("%sun & ph: closed%"),
            opening_hours.like("%sun & ph - closed%"),
            opening_hours.like("%sun and ph: closed%"),
            opening_hours.like("%sunday: closed%"),
            opening_hours.like("%sunday - closed%"),
            opening_hours.like("%sunday closed%"),
            opening_hours.like("%closed on sun%"),
            opening_hours.like("%closed on sunday%"),
            opening_hours.like("%except sun%"),
            opening_hours.like("%except sunday%"),
        )
        return and_(has_sunday_schedule, not_(explicitly_closed))

    return None


def _build_order_by(filters: StructuredFilter) -> list:
    if filters.sort == "rating":
        return [
            func.coalesce(
                Vendor.average_google_rating,
                Vendor.average_rating,
                0.0,
            ).desc(),
            Vendor.name.asc(),
        ]
    if filters.sort == "price_asc":
        return [Vendor.price_range.asc(), Vendor.name.asc()]
    if filters.sort == "price_desc":
        return [Vendor.price_range.desc(), Vendor.name.asc()]
    return [Vendor.name.asc(), Vendor.id.asc()]
