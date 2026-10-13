from fastapi import HTTPException
import os


def validate_filename(filename: str):
    if "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename"
        )

    if filename in {".", ".."}:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename"
        )

    return filename

def get_existing_file(filename: str):
    filename = validate_filename(filename)

    # Retained legacy helper; current document routes use storage identity.
    from app.services.storage_service import local_pdf_path
    file_path = str(local_pdf_path(filename))

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return filename, file_path