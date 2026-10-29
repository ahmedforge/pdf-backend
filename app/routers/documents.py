import os
from uuid import uuid4
from pypdf.errors import PdfReadError, ParseError
from tempfile import mkstemp
from datetime import datetime, timezone
from app.config import settings
from app.services.rate_limit_service import check_rate_limit
from app.schemas.rag import AskRequest
from app.schemas.documents import RenameDocumentRequest
from fastapi.responses import StreamingResponse
import re
from typing import Literal
from app.services.rag_service import (
    ask_document_rag,
    stream_document_rag,
    stream_document_events,
)
from fastapi import Query, APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from app.services.chunk_service import chunk_text
from app.repositories.chunk_repository import (
    get_document_chunks,
    semantic_search_chunks,
)

from app.repositories.document_repository import (
    get_all_documents,
    get_document_by_id,
    delete_document, rename_document, local_storage_key_in_use,
)

from app.security import get_current_user

from app.services.file_service import validate_filename
from app.services.ingestion_service import ingest_document, cleanup_pending_uploads
from app.services.storage_service import (
    storage_settings, open_pdf, local_pdf_path,
)

from app.services.pdf_service import (
    extract_text_from_pdf,
    extract_page_chunks,
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
        # The key is entirely server-generated; names/owners never form a path.
        key = uuid4().hex + ".pdf"
        while local_storage_key_in_use(key):
            key = uuid4().hex + ".pdf"
        path = local_pdf_path(key)
        path.parent.mkdir(exist_ok=True)
        file_path = str(path)

    created = remote
    complete = False
    total_size = 0
    try:
        # Exclusive creation in local mode prevents concurrent overwrites.
        with open(file_path, "wb" if remote else "xb") as buffer:
            created = True
            while chunk := file.file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(413, "File is too large. Maximum size is 10 MiB (10485760 bytes)")
                buffer.write(chunk)

        try:
            chunks = extract_page_chunks(file_path)
        except (PdfReadError, ParseError) as exc:
            raise HTTPException(422, "This PDF is corrupt, encrypted, or unreadable. Upload an unencrypted, readable PDF.") from exc
        if not chunks:
            raise HTTPException(422, "No searchable text chunks were found. The PDF may be scanned, empty, or contain only very short text.")

        document = ingest_document(
            filename, total_size, datetime.now(timezone.utc), current_user.id,
            chunks, file_path,
        )
        complete = True
        logger.info("User %s uploaded %s", current_user.id, filename)
        return {
            "message": "File uploaded successfully",
            "filename": filename,
            "document_id": document.id,
            "id": document.id,
            "display_name": document.display_name or document.filename,
            "size_bytes": document.size_bytes,
            "uploaded_at": document.uploaded_at,
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
        if created and (remote or not complete):
            if remote:
                os.remove(file_path)
            else:
                local_pdf_path(key).unlink(missing_ok=True)


@router.get("/files")
def list_files(
    current_user=Depends(get_current_user)
):
    documents = get_all_documents(current_user.id)
    guest_document_id = getattr(current_user, "guest_document_id", None)
    if guest_document_id is not None:
        documents = [document for document in documents if document["id"] == guest_document_id]

    return {
        "files": documents
    }


@router.patch("/files/{document_id}")
def rename_file(document_id: int, request: RenameDocumentRequest,
                current_user=Depends(get_current_user)):
    document = rename_document(document_id, current_user.id, request.display_name)
    if document is None:
        raise HTTPException(404, "Document not found")
    return {"id": document.id, "filename": document.filename,
            "display_name": document.display_name or document.filename,
            "size_bytes": document.size_bytes, "uploaded_at": document.uploaded_at}


@router.delete("/files/{document_id}")
def delete_file(document_id: int, current_user=Depends(get_current_user)):
    document = delete_document(document_id, current_user.id)
    if document is None:
        raise HTTPException(404, "Document not found")
    try:
        cleanup_pending_uploads(document.storage_key or document.filename)
    except Exception:
        logger.warning("Document deleted; PDF cleanup pending and will retry")
    logger.info("User %s deleted document %s", current_user.id, document_id)
    return {"message": "File deleted successfully", "document_id": document_id,
            "filename": document.filename}


def readable_document(document_id: int, current_user=Depends(get_current_user)):
    document = get_document_by_id(document_id, current_user.id)
    if not document:
        raise HTTPException(404, "Document not found")
    # Request scope keeps the temporary path alive through FileResponse, then
    # closes the context and removes it even if the response fails.
    with open_pdf(document.storage_key or document.filename) as file_path:
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
    stream_format: Literal["text", "sse"] = Query(default="text", alias="format"),
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

    if stream_format == "sse":
        return StreamingResponse(
            stream_document_events(document_id, request.question, request.top_k, min_similarity),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
