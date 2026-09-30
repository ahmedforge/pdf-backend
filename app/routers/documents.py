import os
from tempfile import mkstemp
from datetime import datetime, timezone
from app.config import settings
from app.services.rate_limit_service import check_rate_limit
from app.schemas.rag import AskRequest
from fastapi.responses import StreamingResponse
import re
from app.services.rag_service import (
    ask_document_rag,
    stream_document_rag,
)
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

from app.services.file_service import validate_filename
from app.services.storage_service import (
    storage_settings, persist_pdf, open_pdf, delete_pdf,
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

    remote = storage_settings.file_storage_backend == "supabase"
    if remote:
        fd, file_path = mkstemp(prefix="pdf-upload-", suffix=".pdf")
        os.close(fd)
    else:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", filename)

    created = remote
    stored = False
    complete = False
    document = None
    total_size = 0
    try:
        # Exclusive creation in local mode prevents concurrent overwrites.
        with open(file_path, "wb" if remote else "xb") as buffer:
            created = True
            while chunk := file.file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(413, "File is too large. Maximum size is 10 MB")
                buffer.write(chunk)

        _, text = extract_text_from_pdf(file_path)
        text = clean_extracted_text(text)
        if not text.strip():
            raise HTTPException(422, "No extractable text was found. The PDF may be scanned or image-based.")
        chunks = chunk_text(text)
        if not chunks:
            raise HTTPException(422, "The PDF did not produce any searchable chunks.")

        persist_pdf(filename, file_path)
        stored = remote
        document = insert_document(
            filename, total_size, datetime.now(timezone.utc), current_user.id,
        )
        save_document_chunks(document.id, chunks)
        complete = True
        logger.info("User %s uploaded %s", current_user.id, filename)
        return {
            "message": "File uploaded successfully",
            "filename": filename,
            "document_id": document.id,
            "chunks_created": len(chunks),
        }
    except FileExistsError as exc:
        raise HTTPException(409, "A file with this name already exists") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("PDF upload failed (%s)", type(exc).__name__)
        raise HTTPException(500, "PDF upload processing failed.") from exc
    finally:
        if not complete and document is not None:
            try:
                delete_document(document.id, current_user.id)
            except Exception:
                logger.warning("Failed upload document cleanup requires attention")
        if not complete and stored:
            try:
                delete_pdf(filename)
            except Exception:
                logger.warning("Failed upload storage cleanup requires attention")
        if created and (remote or not complete):
            os.remove(file_path)


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
    delete_pdf(filename)

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


def readable_document(document_id: int, current_user=Depends(get_current_user)):
    document = get_document_by_id(document_id, current_user.id)
    if not document:
        raise HTTPException(404, "Document not found")
    # Request scope keeps the temporary path alive through FileResponse, then
    # closes the context and removes it even if the response fails.
    with open_pdf(document.filename) as file_path:
        yield document, file_path


@router.get("/download/{document_id}")
def download_file(stored=Depends(readable_document, scope="request")):
    document, file_path = stored
    return FileResponse(path=file_path, filename=document.filename, media_type="application/pdf")


@router.get("/extract/{document_id}")
def extract_pdf_text(stored=Depends(readable_document, scope="request")):
    document, file_path = stored
    try:
        reader, text = extract_text_from_pdf(file_path)
        return {
            "document_id": document.id, "filename": document.filename,
            "pages": len(reader.pages), "text": text,
        }
    except Exception as exc:
        raise HTTPException(500, "PDF extraction failed.") from exc


@router.get("/info/{document_id}")
def get_pdf_info(stored=Depends(readable_document, scope="request")):
    document, file_path = stored
    try:
        size = os.path.getsize(file_path)
        reader, text = extract_text_from_pdf(file_path)
        metadata = reader.metadata
        return {
            "document_id": document.id, "filename": document.filename,
            "file_size_bytes": size, "file_size_kb": round(size / 1024, 2),
            "pages": len(reader.pages), "total_characters": len(text),
            "preview": text[:500], "title": metadata.title if metadata else None,
            "author": metadata.author if metadata else None,
            "is_encrypted": reader.is_encrypted,
        }
    except Exception as exc:
        raise HTTPException(500, "PDF info extraction failed.") from exc


@router.get("/search/{document_id}")
def search_pdf_text(query: str, stored=Depends(readable_document, scope="request")):
    document, file_path = stored
    if not query.strip():
        raise HTTPException(400, "Search query cannot be empty")
    try:
        _, text = extract_text_from_pdf(file_path)
        return {
            "document_id": document.id, "filename": document.filename,
            "query": query, "found": query.lower() in text.lower(),
            "matches_count": text.lower().count(query.lower()),
        }
    except Exception as exc:
        raise HTTPException(500, "PDF search failed.") from exc


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
    request: AskRequest,
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
    if not check_rate_limit(current_user.id):
        raise HTTPException(
            status_code=429,
            detail="Too many RAG requests. Please try again later.",
    )

    min_similarity = (
        request.min_similarity
        if request.min_similarity is not None
        else settings.rag_min_similarity
    )

    try:
        rag_result = ask_document_rag(
            document_id=document_id,
            question=request.question,
            top_k=request.top_k,
            min_similarity=min_similarity,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    return {
        "document_id": document_id,
        "question": request.question,
        **rag_result,
    }
@router.post("/files/{document_id}/ask/stream")
def ask_document_stream(
    document_id: int,
    request: AskRequest,
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
    if not check_rate_limit(current_user.id):
        raise HTTPException(
            status_code=429,
            detail="Too many RAG requests. Please try again later.",
    )

    min_similarity = (
        request.min_similarity
        if request.min_similarity is not None
        else settings.rag_min_similarity
    )

    stream = stream_document_rag(
        document_id=document_id,
        question=request.question,
        top_k=request.top_k,
        min_similarity=min_similarity,
    )
    # Read the first token before sending HTTP headers so upstream failures
    # can return a real 503 instead of a broken 200 response.
    try:
        first_chunk = next(stream, "")
    except RuntimeError as exc:
        stream.close()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    def response_body():
        try:
            yield first_chunk
            yield from stream
        except RuntimeError:
            logger.warning("RAG generation interrupted")
            yield "\n\n[Generation interrupted. Please retry your question.]"
        finally:
            stream.close()

    return StreamingResponse(response_body(), media_type="text/plain")
