import re


MIN_CHUNK_TOKENS = 300
MAX_CHUNK_TOKENS = 500
OVERLAP_TOKENS = 75


def count_tokens(text: str) -> int:
    
    words = text.split()

    #
    return int(len(words) * 1.3)


def split_sentences(text: str) -> list[str]:
   
    sentences = re.split(
        r'(?<=[.!?])\s+',
        text.strip()
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def hard_split(text: str, max_tokens: int) -> list[str]:
    
    words = text.split()

    
    max_words = max(1, int(max_tokens / 1.3))

    return [
        " ".join(words[i:i + max_words])
        for i in range(0, len(words), max_words)
    ]


def build_overlap(
    chunk_text: str,
    overlap_tokens: int
) -> str:
    
    sentences = split_sentences(chunk_text)

    overlap_parts = []
    total_tokens = 0

    for sentence in reversed(sentences):
        sentence_tokens = count_tokens(sentence)

        if (
            overlap_parts
            and total_tokens + sentence_tokens > overlap_tokens
        ):
            break

        overlap_parts.insert(0, sentence)
        total_tokens += sentence_tokens

        if total_tokens >= overlap_tokens:
            break

    
    if total_tokens > overlap_tokens * 2:
        words = chunk_text.split()
        overlap_words = max(1, int(overlap_tokens / 1.3))

        return " ".join(words[-overlap_words:])

    return " ".join(overlap_parts)


def chunk_text(
    text: str,
    min_tokens: int = MIN_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS
) -> list[str]:

    if not text or not text.strip():
        return []

    paragraphs = re.split(
        r'\n\s*\n+',
        text.strip()
    )

    paragraphs = [
        paragraph.strip()
        for paragraph in paragraphs
        if paragraph.strip()
    ]

    units = []

    for paragraph in paragraphs:

        
        if count_tokens(paragraph) <= max_tokens:
            units.append(paragraph)
            continue

        
        sentences = split_sentences(paragraph)

        for sentence in sentences:

            if count_tokens(sentence) <= max_tokens:
                units.append(sentence)

            else:
                
                units.extend(
                    hard_split(
                        sentence,
                        max_tokens
                    )
                )

    chunks = []
    current_parts = []

    for unit in units:

        candidate_parts = current_parts + [unit]
        candidate = "\n\n".join(candidate_parts)

        if count_tokens(candidate) <= max_tokens:
            current_parts.append(unit)
            continue

        if current_parts:
            chunk = "\n\n".join(current_parts).strip()

            if chunk:
                chunks.append(chunk)

            overlap = build_overlap(
                chunk,
                overlap_tokens
            )

            current_parts = []

            if overlap:
                current_parts.append(overlap)

        
        candidate = "\n\n".join(
            current_parts + [unit]
        )

        if count_tokens(candidate) <= max_tokens:
            current_parts.append(unit)

        else:
            
            for piece in hard_split(unit, max_tokens):
                if current_parts:
                    chunk = "\n\n".join(current_parts).strip()

                    if chunk:
                        chunks.append(chunk)

                overlap = (
                    build_overlap(
                        chunks[-1],
                        overlap_tokens
                    )
                    if chunks
                    else ""
                )

                current_parts = []

                if overlap:
                    current_parts.append(overlap)

                current_parts.append(piece)

    if current_parts:
        final_chunk = "\n\n".join(current_parts).strip()

        if final_chunk:
            chunks.append(final_chunk)

    return chunks