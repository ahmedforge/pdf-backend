from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models.chunk import Chunk


def save_document_chunks(
    document_id: int,
    chunks: list[str]
):
    with SessionLocal() as db:
        db.execute(
            delete(Chunk).where(
                Chunk.document_id == document_id
            )
        )

        chunk_rows = [
            Chunk(
                document_id=document_id,
                chunk_index=index,
                chunk_text=chunk_text
            )
            for index, chunk_text in enumerate(chunks)
        ]

        db.add_all(chunk_rows)
        db.commit()

        return chunk_rows


def get_document_chunks(
    document_id: int,
    limit: int = 5
):
    with SessionLocal() as db:
        chunks = db.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
            .limit(limit)
        ).all()

        return [
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.chunk_text
            }
            for chunk in chunks
        ]