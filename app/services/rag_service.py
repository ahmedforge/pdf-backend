import re

from app.repositories.chunk_repository import semantic_search_chunks
from app.services.llm.factory import get_llm_provider
from app.config import settings
from collections.abc import Iterator
from time import perf_counter
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

    # Fallback for short/small documents:
    # if nothing clears the threshold, still give the LLM
    # the single best retrieved chunk.
    if not relevant_chunks and chunks:
        relevant_chunks = [chunks[0]]

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
- Do not guess facts that are not supported by the context.
- Infer reasonable conclusions when the context strongly supports them.
- If multiple retrieved chunks repeatedly focus on the same character or subject,
  you may conclude that character or subject is central to the document.
- If the context truly does not contain enough information, say:
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
def stream_document_rag(
    document_id: int,
    question: str,
    top_k: int = 5,
    min_similarity: float = 0.30,
) -> Iterator[str]:
    total_start = perf_counter()

    retrieval_start = perf_counter()

    chunks = semantic_search_chunks(
        document_id=document_id,
        query=question,
        limit=top_k,
    )

    retrieval_time = perf_counter() - retrieval_start

    relevant_chunks = [
        chunk
        for chunk in chunks
        if chunk["similarity"] >= min_similarity
    ]

    if not relevant_chunks and chunks:
        relevant_chunks = [chunks[0]]

    if not relevant_chunks:
        total_time = perf_counter() - total_start

    print(
        f"[RAG TIMING] retrieval={retrieval_time:.2f}s "
        f"generation=0.00s "
        f"total={total_time:.2f}s"
    )

    yield "I could not find the answer in the document."
    return

    prompt = f"""
You are answering a question using only the document context below.

Rules:
- Use only the provided context.
- Do not use outside knowledge.
- Do not guess facts that are not supported by the context.
- Infer reasonable conclusions when the context strongly supports them.
- If multiple retrieved chunks repeatedly focus on the same character or subject,
  you may conclude that character or subject is central to the document.
- If the context truly does not contain enough information, say:
  "I could not find the answer in the document."
- Cite supporting chunks using this format: [Chunk 12]
- Only cite chunk numbers that appear in the provided context.

Context:
{context}

Question:
{question}

Answer:
"""

    generation_start = perf_counter()

    first_chunk_received = False

    for chunk in llm.stream(prompt):
        if not first_chunk_received:
            first_token_time = perf_counter() - generation_start

            print(
                f"[RAG TIMING] time_to_first_token={first_token_time:.2f}s"
            )

            first_chunk_received = True

        yield chunk

    generation_time = perf_counter() - generation_start
    total_time = perf_counter() - total_start

    print(
        f"[RAG TIMING] retrieval={retrieval_time:.2f}s "
        f"generation={generation_time:.2f}s "
        f"total={total_time:.2f}s"
    )