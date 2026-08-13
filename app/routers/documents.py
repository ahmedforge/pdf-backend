import os
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse

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

from app.services.pdf_service import extract_text_from_pdf
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

    insert_document(
        filename,
        size_bytes,
        uploaded_at,
        current_user.id
    )
    insert_document(
    filename,
    size_bytes,
    uploaded_at,
    current_user.id
    )

    return {
        "message": "File uploaded successfully",
        "filename": filename
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