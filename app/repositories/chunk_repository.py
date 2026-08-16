from sqlalchemy import delete, select
from app.services.embedding_service import generate_embedding

from app.database import SessionLocal
from app.models.chunk import Chunk
from app.services.embedding_service import generate_embeddings


def save_document_chunks(
    document_id: int,
    chunks: list[str]
):
    embeddings = generate_embeddings(chunks)

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
                chunk_text=chunk_text,
                embedding=embeddings[index]
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
def semantic_search_chunks(
    document_id: int,
    query: str,
    limit: int = 5,
):
    query_embedding = generate_embedding(query)

    with SessionLocal() as db:
        chunks = db.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .where(Chunk.embedding.is_not(None))
            .order_by(
                Chunk.embedding.cosine_distance(query_embedding)
            )
            .limit(limit)
        ).all()

        return [
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.chunk_text,
            }
            for chunk in chunks
        ]