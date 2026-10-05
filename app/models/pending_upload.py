"""Recovery journal for objects that do not yet belong to a committed document."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PendingUpload(Base):
    __tablename__ = "pending_uploads"
    storage_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
