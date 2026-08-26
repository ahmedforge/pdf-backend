import os
from datetime import datetime, timezone
from app.services.llm_service import generate_answer
from app.config import settings
import re

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from app.services.chunk_service import chunk_text
from app.repositories.chunk_repository import (
    save_document_chunks,
    get_document_chunks,
    semantic_search_chunks,
)

from app.repositories.document_repository import (
    insert_document,
    get_all_documents,
    get_document_by_id,
    delete_document
)

from app.security import get_current_user

from app.services.file_service import (
    validate_filename,
    get_existing_file
)

from app.services.pdf_service import (
    extract_text_from_pdf,
    clean_extracted_text
)
import logging

logger = logging.getLogger(__name__)


router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is missing"
        )

    filename = validate_filename(file.filename)

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    header = file.file.read(5)
    file.file.seek(0)

    if header != b"%PDF-":
        raise HTTPException(
            status_code=400,
            detail="File content is not a valid PDF"
        )

    file_path = os.path.join("uploads", filename)

    if os.path.exists(file_path):
        raise HTTPException(
            status_code=409,
            detail="A file with this name already exists"
        )

    total_size = 0
    chunk_size = 1024 * 1024

    try:
        with open(file_path, "wb") as buffer:
            while True:
                chunk = file.file.read(chunk_size)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File is too large. Maximum size is 10 MB"
                    )

                buffer.write(chunk)

    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)

        raise

    size_bytes = os.path.getsize(file_path)
    uploaded_at = datetime.now(timezone.utc)

    
    document = insert_document(
    filename,
    size_bytes,
    uploaded_at,
    current_user.id
    )
    reader, text = extract_text_from_pdf(file_path)

    text = clean_extracted_text(text)

    chunks = chunk_text(text)

    save_document_chunks(
    document.id,
    chunks
    )

    logger.info(
    "User %s uploaded %s",
    current_user.id,
    filename
    )

    return {
    "message": "File uploaded successfully",
    "filename": filename,
    "document_id": document.id,
    "chunks_created": len(chunks)
    }


@router.get("/files")
def list_files(
    current_user=Depends(get_current_user)
):
    documents = get_all_documents(current_user.id)

    return {
        "files": documents
    }


@router.delete("/files/{document_id}")
def delete_file(
    document_id: int,
    current_user=Depends(get_current_user)
):
    document = get_document_by_id(
        document_id,
        current_user.id
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    filename = document.filename
    filename, file_path = get_existing_file(filename)

    os.remove(file_path)

    delete_document(
        document_id,
        current_user.id
    )
    logger.info(
    "User %s deleted document %s",
    current_user.id,
    document_id
    )

    return {
        "message": "File deleted successfully",
        "document_id": document_id,
        "filename": filename
    }


@router.get("/download/{document_id}")
def download_file(
    document_id: int,
    current_user=Depends(get_current_user)
):
    document = get_document_by_id(
        document_id,
        current_user.id
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    filename = document.filename
    filename, file_path = get_existing_file(filename)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/pdf"
    )


@router.get("/extract/{document_id}")
def extract_pdf_text(
    document_id: int,
    current_user=Depends(get_current_user)
):
    document = get_document_by_id(
        document_id,
        current_user.id
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    filename = document.filename
    filename, file_path = get_existing_file(filename)

    try:
        reader, text = extract_text_from_pdf(file_path)

        return {
            "document_id": document_id,
            "filename": filename,
            "pages": len(reader.pages),
            "text": text
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF extraction failed: {str(e)}"
        )


@router.get("/info/{document_id}")
def get_pdf_info(
    document_id: int,
    current_user=Depends(get_current_user)
):
    document = get_document_by_id(
        document_id,
        current_user.id
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    filename = document.filename
    filename, file_path = get_existing_file(filename)

    try:
        file_size_bytes = os.path.getsize(file_path)
        file_size_kb = round(file_size_bytes / 1024, 2)

        reader, text = extract_text_from_pdf(file_path)
        metadata = reader.metadata

        return {
            "document_id": document_id,
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "file_size_kb": file_size_kb,
            "pages": len(reader.pages),
            "total_characters": len(text),
            "preview": text[:500],
            "title": metadata.title if metadata else None,
            "author": metadata.author if metadata else None,
            "is_encrypted": reader.is_encrypted
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF info extraction failed: {str(e)}"
        )


@router.get("/search/{document_id}")
def search_pdf_text(
    document_id: int,
    query: str,
    current_user=Depends(get_current_user)
):
    document = get_document_by_id(
        document_id,
        current_user.id
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    filename = document.filename
    filename, file_path = get_existing_file(filename)

    if not query.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty"
        )

    try:
        _, text = extract_text_from_pdf(file_path)

        lower_text = text.lower()
        lower_query = query.lower()

        return {
            "document_id": document_id,
            "filename": filename,
            "query": query,
            "found": lower_query in lower_text,
            "matches_count": lower_text.count(lower_query)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF search failed: {str(e)}"
        )



@router.get("/files/{document_id}/chunks")
def list_document_chunks(
    document_id: int,
    limit: int = 5,
    current_user=Depends(get_current_user)
):
    document = get_document_by_id(
        document_id,
        current_user.id
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    chunks = get_document_chunks(
        document_id,
        limit
    )

    return {
        "document_id": document_id,
        "returned_chunks": len(chunks),
        "chunks": chunks
    }
@router.get("/files/{document_id}/semantic-search")
def semantic_search_document(
    document_id: int,
    query: str,
    limit: int = 5,
    current_user=Depends(get_current_user),
):
    document = get_document_by_id(
        document_id,
        current_user.id,
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if not query.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty",
        )

    if limit < 1 or limit > 20:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 20",
        )

    results = semantic_search_chunks(
        document_id=document_id,
        query=query,
        limit=limit,
    )

    return {
        "document_id": document_id,
        "query": query,
        "returned_chunks": len(results),
        "results": results,
    }
@router.post("/files/{document_id}/ask")
def ask_document(
    document_id: int,
    question: str,
    top_k: int = 5,
    min_similarity: float = settings.rag_min_similarity,
    current_user=Depends(get_current_user),
):
    document = get_document_by_id(
        document_id,
        current_user.id,
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if not question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty",
        )

    if top_k < 1 or top_k > 10:
        raise HTTPException(
            status_code=400,
            detail="top_k must be between 1 and 10",
        )

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
            "document_id": document_id,
            "question": question,
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

    try:
        answer = generate_answer(prompt)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    cited_chunk_indexes = {
        int(match)
        for match in re.findall(r"\[Chunk (\d+)\]", answer)
    }

    valid_chunk_indexes = {
        chunk["chunk_index"]
        for chunk in relevant_chunks
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
        "document_id": document_id,
        "question": question,
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