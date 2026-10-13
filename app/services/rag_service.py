import re
import json

from app.repositories.chunk_repository import semantic_search_chunks
from app.services.llm.factory import get_llm_provider
from app.config import settings
from collections.abc import Iterator
from time import perf_counter
llm = get_llm_provider()
def _retrieve_context(
    document_id: int,
    question: str,
    top_k: int,
    min_similarity: float,
) -> tuple[list[dict], str]:
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
        return [], ""

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

    return relevant_chunks, prompt


def ask_document_rag(
    document_id: int,
    question: str,
    top_k: int = 5,
    min_similarity: float | None = None,
) -> dict:
    if min_similarity is None:
        min_similarity = settings.rag_min_similarity

    relevant_chunks, prompt = _retrieve_context(
        document_id, question, top_k, min_similarity
    )
    if not relevant_chunks:
        return {
            "answer": "I could not find the answer in the document.",
            "sources": [],
        }

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
        "sources": build_sources(relevant_chunks),
    }
def stream_document_rag(
    document_id: int,
    question: str,
    top_k: int = 5,
    min_similarity: float | None = None,
) -> Iterator[str]:
    total_start = perf_counter()

    retrieval_start = perf_counter()

    if min_similarity is None:
        min_similarity = settings.rag_min_similarity
    relevant_chunks, prompt = _retrieve_context(
        document_id, question, top_k, min_similarity
    )
    retrieval_time = perf_counter() - retrieval_start
    if not relevant_chunks:
        yield "I could not find the answer in the document."
        return

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


def build_sources(chunks):
    return [{
        "chunk_index": chunk["chunk_index"],
        "page": chunk.get("page_number"),
        "text": chunk["chunk_text"],
        "similarity": chunk["similarity"],
        "preview": chunk["chunk_text"][:300],
    } for chunk in chunks]


def validated_tokens(tokens, valid_indexes):
    """Hold only possible citation markers, including markers split across tokens."""
    prefix = "[Chunk "
    pending = ""
    for token in tokens:
        pending += token
        while pending:
            start = pending.find(prefix)
            if start < 0:
                keep = next((size for size in range(len(prefix)-1, 0, -1)
                             if pending.endswith(prefix[:size])), 0)
                safe = len(pending) - keep
                if safe:
                    yield pending[:safe]
                    pending = pending[safe:]
                break
            if start:
                yield pending[:start]
                pending = pending[start:]
            end = pending.find("]")
            if end < 0:
                if re.fullmatch(r"\[Chunk \d*", pending):
                    break
                yield pending[0]
                pending = pending[1:]
                continue
            marker = pending[:end+1]
            match = re.fullmatch(r"\[Chunk (\d+)\]", marker)
            if not match or int(match.group(1)) in valid_indexes:
                yield marker
            pending = pending[end+1:]
    if pending:
        yield pending


def sse_event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_document_events(document_id, question, top_k=5, min_similarity=None):
    """Opt-in protocol: sources, token*, done; failures add an error event."""
    if min_similarity is None:
        min_similarity = settings.rag_min_similarity
    try:
        chunks, prompt = _retrieve_context(document_id, question, top_k, min_similarity)
    except Exception:
        yield sse_event("sources", {"sources": []})
        yield sse_event("error", {"message": "Document retrieval is unavailable. Please retry."})
        yield sse_event("done", {"complete": False})
        return
    yield sse_event("sources", {"sources": build_sources(chunks)})
    if not chunks:
        yield sse_event("token", {"text": "I could not find the answer in the document."})
        yield sse_event("done", {"complete": True})
        return
    tokens = None
    try:
        tokens = llm.stream(prompt)
        for token in validated_tokens(tokens, {chunk["chunk_index"] for chunk in chunks}):
            if token:
                yield sse_event("token", {"text": token})
    except Exception:
        yield sse_event("error", {"message": "Answer generation was interrupted. Please retry."})
        yield sse_event("done", {"complete": False})
        return
    finally:
        if tokens is not None:
            close = getattr(tokens, "close", None)
            if close:
                close()
    yield sse_event("done", {"complete": True})
