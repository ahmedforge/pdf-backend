from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    chunk_index: Mapped[int] = mapped_column(
        nullable=False
    )

    chunk_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    embedding: Mapped[list[float] | None] = mapped_column(
    Vector(1536),
    nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunk_index"
        ),
    )