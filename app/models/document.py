from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=True
        )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    __table_args__ = (UniqueConstraint("owner_id", "filename", name="uq_documents_owner_filename"),)
