from __future__ import annotations

import pymupdf
import pytest

from panel_rag.pdf_loader import PdfReadError, extract_pdf_pages


def make_pdf(*page_texts: str) -> bytes:
    document = pymupdf.open()
    try:
        for text in page_texts:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def test_extracts_text_with_one_based_page_numbers() -> None:
    pages = extract_pdf_pages(make_pdf("first", "second"), "manual.pdf")

    assert [item.page_number for item in pages] == [1, 2]
    assert [item.text for item in pages] == ["first", "second"]


def test_rejects_pdf_without_extractable_text() -> None:
    with pytest.raises(PdfReadError, match="OCR"):
        extract_pdf_pages(make_pdf(""), "scan.pdf")

