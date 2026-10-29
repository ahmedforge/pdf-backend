"""Validate or migrate local PDFs through the application's ingestion flow.

Run from the backend folder, with its private .env. Register the owner in the
PDF app first. Original files are never removed. Re-runs verify existing bytes.
"""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException, UploadFile
from app.repositories.document_repository import get_all_documents, get_document_by_id
from app.repositories.user_repository import get_user_by_email
from app.routers.documents import MAX_FILE_SIZE, upload_file
from app.services.file_service import validate_filename
from app.services.pdf_service import clean_extracted_text, extract_text_from_pdf
from app.services.storage_service import open_pdf, storage_settings


def validate_pdf(path):
    validate_filename(path.name)
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("PDF exceeds the 10 MiB (10485760 bytes) limit")
    with path.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise ValueError("File is not a PDF")
    _, text = extract_text_from_pdf(str(path))
    if not clean_extracted_text(text).strip():
        raise ValueError("No extractable text; OCR is required before RAG ingestion")


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").digest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uploads-dir", default="uploads")
    parser.add_argument("--owner-email")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = Path(args.uploads_dir)
    if not folder.is_dir():
        parser.error("Uploads directory does not exist")
    owner = None
    original_names = {}
    if folder.resolve() == Path("uploads").resolve():
        # A shared application directory is not an import folder. Read only the
        # selected owner's recorded physical keys; never adopt another owner's
        # PDF or a UUID filename as the display/original name.
        if not args.owner_email:
            parser.error("Shared uploads requires --owner-email, including dry runs")
        owner = get_user_by_email(args.owner_email.lower())
        if owner is None:
            parser.error("Owner account not found")
        files = []
        from app.services.storage_service import local_pdf_path
        for item in get_all_documents(owner.id):
            document = get_document_by_id(item["id"], owner.id)
            if document is None:
                parser.error("Document changed during inventory; retry")
            path = local_pdf_path(document.storage_key or document.filename)
            if not path.is_file():
                parser.error("An owned local PDF is missing; use an explicit export folder for remote documents")
            files.append(path)
            original_names[path] = document.filename
    else:
        # An explicit separate export directory is assigned to the selected
        # owner by the operator. Symlinks are rejected, not followed.
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf")
        if any(p.is_symlink() or not p.is_file() for p in files):
            parser.error("Export PDFs must be regular files, not symlinks")
    print(f"PDFs found: {len(files)}")
    failures = []
    for path in files:
        try:
            validate_pdf(path)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            failures.append((path.name, reason))
    for name, reason in failures:
        print(f"Validation failed: {name}: {reason}")
    if failures:
        print("No files migrated. Fix validation failures before retrying.")
        return 1
    print("PDF validation passed.")
    if args.dry_run:
        print("Dry run: no database or storage writes.")
        return 0
    if storage_settings.file_storage_backend != "supabase":
        parser.error("FILE_STORAGE_BACKEND must be supabase")
    if not args.owner_email:
        parser.error("Provide --owner-email for the registered PDF app account")
    owner = owner or get_user_by_email(args.owner_email.lower())
    if owner is None:
        print("Owner account not found. Register this email in the PDF app first.")
        return 1
    existing = {item["filename"]: item["id"] for item in get_all_documents(owner.id)}
    migrated = skipped = 0
    for path in files:
        filename = original_names.get(path, path.name)
        if filename in existing:
            document = get_document_by_id(existing[filename], owner.id)
            with open_pdf(document.storage_key or document.filename) as saved:
                if digest(saved) != digest(path):
                    print(f"Conflict: {path.name} differs from the existing stored PDF. Nothing overwritten.")
                    return 1
            skipped += 1
            print(f"Already migrated and verified: {path.name}")
            continue
        try:
            with path.open("rb") as source:
                result = upload_file(UploadFile(filename=filename, file=source), current_user=owner)
        except HTTPException as exc:
            print(f"Migration failed: {path.name}: HTTP {exc.status_code}. Re-run after fixing the failure.")
            return 1
        migrated += 1
        print(f"Migrated: {path.name}: {result['chunks_created']} chunks")
    print(f"Complete: {migrated} migrated, {skipped} previously migrated; original files retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
