"""Regenerate the original public guest sample from its reviewable JSON source."""
import json
from pathlib import Path
from evaluate_answers import pdf_bytes

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / 'demo/sample-guide.json').read_text())
    (root / 'demo/sample-guide.pdf').write_bytes(pdf_bytes(source))
