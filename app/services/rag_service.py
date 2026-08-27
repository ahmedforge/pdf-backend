import re

from app.repositories.chunk_repository import semantic_search_chunks
from app.services.llm.factory import get_llm_provider
from app.config import settings

llm = get_llm_provider()
def ask_document_rag(
    document_id: int,
    question: str,
    top_k: int = 5,
    min_similarity: float | None = None,
) -> dict:
    if min_similarity is None:
        min_similarity = settings.rag_min_similarity

    chunks = semantic_search_chunks(
        document_id=document_id,
        query=question,
        limit=top_k,
    )

    relevant_chunks = [
        chunk
        for chunk in chunks
        if chunk["similarity"] >= min_similarity
    ]

    if not relevant_chunks:
        return {
            "answer": "I could not find the answer in the document.",
            "sources": [],
        }

    context = "\n\n".join(
        f"[Chunk {chunk['chunk_index']}]\n{chunk['chunk_text']}"
        for chunk in relevant_chunks
    )

    prompt = f"""
You are answering a question using only the document context below.

Rules:
- Use only the provided context.
- Do not use outside knowledge.
- Do not guess.
- If the context is insufficient, say:
  "I could not find the answer in the document."
- Cite supporting chunks using this format: [Chunk 12]
- Only cite chunk numbers that appear in the provided context.

Context:
{context}

Question:
{question}

Answer:
"""

    answer = llm.generate(prompt)

    valid_chunk_indexes = {
        chunk["chunk_index"]
        for chunk in relevant_chunks
    }

    cited_chunk_indexes = {
        int(match)
        for match in re.findall(r"\[Chunk (\d+)\]", answer)
    }

    invalid_citations = (
        cited_chunk_indexes - valid_chunk_indexes
    )

    if invalid_citations:
        answer = re.sub(
            r"\[Chunk (\d+)\]",
            lambda match: (
                match.group(0)
                if int(match.group(1)) in valid_chunk_indexes
                else ""
            ),
            answer,
        ).strip()

    return {
        "answer": answer,
        "sources": [
            {
                "chunk_index": chunk["chunk_index"],
                "similarity": chunk["similarity"],
                "preview": chunk["chunk_text"][:300],
            }
            for chunk in relevant_chunks
        ],
    }