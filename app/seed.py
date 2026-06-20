from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User


def seed_first_admin(db: Session) -> None:
    """Create the first admin from env settings if there are no users yet."""
    existing = db.scalar(select(User).limit(1))
    if existing is not None:
        return

    admin = User(
        username=settings.first_admin_username,
        email=settings.first_admin_email,
        hashed_password=hash_password(settings.first_admin_password),
        is_admin=True,
        is_active=True,
    )
    db.add(admin)
    db.commit()
