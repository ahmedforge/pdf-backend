from pypdf import PdfReader


def extract_text_from_pdf(file_path: str):
    reader = PdfReader(file_path)

    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    return reader, text
import re
from collections import Counter


def clean_extracted_text(text: str) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    counts = Counter(lines)

    # Remove lines repeated many times,
    # usually headers, footers, watermarks, etc.
    cleaned_lines = [
        line
        for line in lines
        if counts[line] <= 3
    ]

    cleaned_text = "\n".join(cleaned_lines)

    # Collapse excessive spaces
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)

    # Collapse too many blank lines
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()
import re
from collections import Counter


def clean_extracted_text(text: str) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    counts = Counter(lines)

    # Remove lines repeated many times,
    # usually headers, footers, watermarks, etc.
    cleaned_lines = [
        line
        for line in lines
        if counts[line] <= 3
    ]

    cleaned_text = "\n".join(cleaned_lines)

    # Collapse excessive spaces
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)

    # Collapse too many blank lines
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()

MIN_CHUNK_CHARACTERS = 20


def extract_page_chunks(file_path: str) -> list[dict]:
    """Physical PDF pages are 1-based; chunks never cross a page boundary."""
    from app.services.chunk_service import chunk_text
    reader = PdfReader(file_path)
    chunks = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = clean_extracted_text(page.extract_text() or "")
        for value in chunk_text(text):
            if len(re.sub(r"\s", "", value)) >= MIN_CHUNK_CHARACTERS:
                chunks.append({"chunk_text": value, "page_number": page_number})
    return chunks
