from __future__ import annotations

from .models import PageText, TextChunk


def chunk_pages(
    pages: list[PageText],
    *,
    document_id: str,
    file_name: str,
    max_chars: int = 900,
    overlap_chars: int = 150,
) -> list[TextChunk]:
    if max_chars < 100:
        raise ValueError("max_chars は100以上で指定してください。")
    if not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap_chars は0以上かつmax_chars未満です。")

    chunks: list[TextChunk] = []
    for page in pages:
        for chunk_index, text in enumerate(
            _split_text(page.text, max_chars=max_chars, overlap_chars=overlap_chars)
        ):
            chunks.append(
                TextChunk(
                    chunk_id=(
                        f"{document_id}:page-{page.page_number}:chunk-{chunk_index}"
                    ),
                    document_id=document_id,
                    file_name=file_name,
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    text=text,
                )
            )
    return chunks


def _split_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    boundaries = ("\n", "。", "！", "？", ". ", "; ", " ")

    while start < len(text):
        hard_end = min(start + max_chars, len(text))
        end = hard_end

        if hard_end < len(text):
            minimum = start + max_chars // 2
            best = -1
            best_width = 0
            window = text[minimum:hard_end]
            for boundary in boundaries:
                position = window.rfind(boundary)
                if position >= 0 and minimum + position > best:
                    best = minimum + position
                    best_width = len(boundary)
            if best >= minimum:
                end = best + best_width

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break

        next_start = max(end - overlap_chars, start + 1)
        start = next_start

    return chunks

