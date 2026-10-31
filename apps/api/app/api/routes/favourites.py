from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.models import UserFavourite, Vendor
from app.schemas.favourite import (
    FavouriteListRead,
    FavouriteRead,
    FavouriteStateRead,
    FavouriteVendorRead,
)


router = APIRouter(prefix="/auth/me/favourites", tags=["favourites"])
VendorId = Annotated[int, Path(gt=0)]


def require_vendor(session: DbSession, vendor_id: int) -> None:
    if session.get(Vendor, vendor_id) is None:
        raise HTTPException(status_code=404, detail="Vendor not found")


@router.get("", response_model=FavouriteListRead)
def list_my_favourites(
    current_user: CurrentUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FavouriteListRead:
    owned = UserFavourite.user_id == current_user.id
    total = session.scalar(select(func.count()).select_from(UserFavourite).where(owned))
    favourites = session.scalars(
        select(UserFavourite)
        .options(selectinload(UserFavourite.vendor))
        .where(owned)
        .order_by(UserFavourite.created_at.desc(), UserFavourite.vendor_id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return FavouriteListRead(
        items=[
            FavouriteRead(
                vendor=FavouriteVendorRead(id=item.vendor.id, name=item.vendor.name),
                created_at=item.created_at,
            )
            for item in favourites
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{vendor_id}", response_model=FavouriteStateRead)
def read_my_favourite(
    vendor_id: VendorId,
    current_user: CurrentUser,
    session: DbSession,
) -> FavouriteStateRead:
    require_vendor(session, vendor_id)
    created_at = session.scalar(
        select(UserFavourite.created_at).where(
            UserFavourite.user_id == current_user.id,
            UserFavourite.vendor_id == vendor_id,
        )
    )
    return FavouriteStateRead(
        vendor_id=vendor_id, favourited=created_at is not None, created_at=created_at,
    )


@router.put("/{vendor_id}", response_model=FavouriteStateRead)
def favourite_vendor(
    vendor_id: VendorId,
    current_user: CurrentUser,
    session: DbSession,
) -> FavouriteStateRead:
    require_vendor(session, vendor_id)
    insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgres_insert
    # The composite primary key and atomic upsert also protect concurrent requests.
    statement = insert(UserFavourite).values(
        user_id=current_user.id,
        vendor_id=vendor_id,
        created_at=datetime.now(timezone.utc),
    )
    created_at = session.scalar(
        statement.on_conflict_do_update(
            index_elements=[UserFavourite.user_id, UserFavourite.vendor_id],
            set_={"created_at": statement.excluded.created_at},
        ).returning(UserFavourite.created_at)
    )
    session.commit()
    return FavouriteStateRead(
        vendor_id=vendor_id, favourited=True, created_at=created_at,
    )


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfavourite_vendor(
    vendor_id: VendorId,
    current_user: CurrentUser,
    session: DbSession,
) -> Response:
    require_vendor(session, vendor_id)
    session.execute(
        delete(UserFavourite).where(
            UserFavourite.user_id == current_user.id,
            UserFavourite.vendor_id == vendor_id,
        )
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
