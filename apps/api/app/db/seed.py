from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User, Vendor


DEMO_VENDORS = (
    {
        "name": "Demo Vendor 1",
        "location": "Demo Canteen",
        "category": "Demo",
        "opening_hours": "09:00 - 21:00",
    },
    {
        "name": "Demo Vendor 2",
        "location": "Demo Canteen",
        "category": "Demo",
        "opening_hours": "10:00 - 22:00",
    },
)


def _seed_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str,
) -> tuple[User, bool]:
    existing_user = session.scalar(select(User).where(User.username == username))

    if existing_user is not None:
        if existing_user.role != role:
            existing_user.role = role
            session.commit()
        return existing_user, False

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user, True


def seed_development_admin(session: Session) -> tuple[User, bool]:
    return _seed_user(
        session,
        username=settings.seed_admin_username,
        password=settings.seed_admin_password.get_secret_value(),
        role="admin",
    )


def seed_development_user(session: Session) -> tuple[User, bool]:
    return _seed_user(
        session,
        username=settings.seed_test_username,
        password=settings.seed_test_password.get_secret_value(),
        role="user",
    )


def seed_demo_vendors(session: Session) -> list[tuple[Vendor, bool]]:
    results: list[tuple[Vendor, bool]] = []

    for vendor_data in DEMO_VENDORS:
        vendor = session.scalar(
            select(Vendor).where(Vendor.name == vendor_data["name"]).limit(1)
        )
        if vendor is not None:
            results.append((vendor, False))
            continue

        vendor = Vendor(**vendor_data)
        session.add(vendor)
        session.commit()
        session.refresh(vendor)
        results.append((vendor, True))

    return results


def main() -> None:
    with SessionLocal() as session:
        admin, admin_created = seed_development_admin(session)
        test_user, test_user_created = seed_development_user(session)
        vendors = seed_demo_vendors(session)

    admin_action = "Created" if admin_created else "Confirmed"
    user_action = "Created" if test_user_created else "Confirmed"
    print(
        f"{admin_action} local administrator account: "
        f"{admin.username} (id={admin.id})"
    )
    print(
        f"{user_action} local test account: "
        f"{test_user.username} (id={test_user.id})"
    )
    for vendor, created in vendors:
        action = "Created" if created else "Confirmed"
        print(f"{action} demo vendor: {vendor.name} (id={vendor.id})")


if __name__ == "__main__":
    main()
