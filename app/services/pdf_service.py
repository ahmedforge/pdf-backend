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