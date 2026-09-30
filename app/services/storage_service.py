"""Durable PDF storage; Supabase files are downloaded only to temporary paths."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.file_service import validate_filename


class StorageSettings(BaseSettings):
    file_storage_backend: Literal['local', 'supabase'] = 'local'
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str = 'pdfs'
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', hide_input_in_errors=True)

    @model_validator(mode='after')
    def require_supabase_credentials(self):
        if self.file_storage_backend == 'supabase':
            if not self.supabase_url or not self.supabase_url.startswith('https://'):
                raise ValueError('SUPABASE_URL must be an HTTPS project URL')
            if not self.supabase_service_role_key or not self.supabase_service_role_key.get_secret_value():
                raise ValueError('SUPABASE_SERVICE_ROLE_KEY is required')
            if not self.supabase_storage_bucket:
                raise ValueError('SUPABASE_STORAGE_BUCKET is required')
        return self


storage_settings = StorageSettings()
MAX_PDF_BYTES = 10 * 1024 * 1024
TIMEOUT = httpx.Timeout(connect=10, read=60, write=60, pool=10)


def _headers():
    key = storage_settings.supabase_service_role_key.get_secret_value()
    return {'Authorization': f'Bearer {key}', 'apikey': key}


def _url(filename=None, *, download=False):
    base = storage_settings.supabase_url.rstrip('/') + '/storage/v1/object/'
    if download:
        base += 'authenticated/'
    base += quote(storage_settings.supabase_storage_bucket, safe='')
    if filename is not None:
        base += '/' + quote(validate_filename(filename), safe='')
    return base


def _check_response(response, *, upload=False):
    if response.is_success:
        return
    # Older Storage API versions wrap a semantic status in an HTTP 400.
    try:
        data = response.json()
        status = str(data.get('statusCode', response.status_code)) if isinstance(data, dict) else str(response.status_code)
    except ValueError:
        status = str(response.status_code)
    if status == '404' and not upload:
        raise HTTPException(404, 'File not found')
    if status == '409' and upload:
        raise HTTPException(409, 'A file with this name already exists')
    raise HTTPException(503, 'PDF storage is unavailable. Please try again later.')


def persist_pdf(filename: str, file_path: str):
    """Upload without overwriting an existing object; local mode is a no-op."""
    filename = validate_filename(filename)
    if storage_settings.file_storage_backend == 'local':
        return
    try:
        with open(file_path, 'rb') as source, httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(
                _url(filename), content=source,
                headers={**_headers(), 'Content-Type': 'application/pdf', 'x-upsert': 'false'},
            )
            _check_response(response, upload=True)
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'PDF storage is unavailable. Please try again later.') from exc


@contextmanager
def open_pdf(filename: str):
    """Yield a readable path; always remove temporary Supabase downloads."""
    filename = validate_filename(filename)
    if storage_settings.file_storage_backend == 'local':
        path = Path('uploads') / filename
        if not path.is_file():
            raise HTTPException(404, 'File not found')
        yield str(path)
        return
    path = None
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            with client.stream('GET', _url(filename, download=True), headers=_headers()) as response:
                if not response.is_success:
                    response.read()
                _check_response(response)
                with NamedTemporaryFile(prefix='pdf-rag-', suffix='.pdf', delete=False) as target:
                    path = Path(target.name)
                    size = 0
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > MAX_PDF_BYTES:
                            raise HTTPException(413, 'Stored PDF exceeds the 10 MB limit')
                        target.write(chunk)
        yield str(path)
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'PDF storage is unavailable. Please try again later.') from exc
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def delete_pdf(filename: str):
    filename = validate_filename(filename)
    if storage_settings.file_storage_backend == 'local':
        (Path('uploads') / filename).unlink(missing_ok=True)
        return
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request('DELETE', _url(), headers=_headers(), json={'prefixes': [filename]})
            _check_response(response)
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'PDF storage is unavailable. Please try again later.') from exc
