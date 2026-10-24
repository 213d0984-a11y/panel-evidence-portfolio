from __future__ import annotations

import re

import pymupdf

from .models import PageText


class PdfReadError(ValueError):
    """PDFをMVPの対象として読み取れない場合。"""


def extract_pdf_pages(pdf_bytes: bytes, file_name: str) -> list[PageText]:
    if not pdf_bytes:
        raise PdfReadError(f"{file_name}: ファイルが空です。")
    if len(pdf_bytes)>50*1024*1024:
        raise PdfReadError(f"{file_name}: 50MBを超えるPDFは対象外です。")

    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfReadError(f"{file_name}: PDFを開けませんでした。") from exc

    try:
        if document.needs_pass:
            raise PdfReadError(f"{file_name}: パスワード付きPDFは対象外です。")
        if len(document)>500:
            raise PdfReadError(f"{file_name}: 500ページを超えるPDFは対象外です。")

        pages: list[PageText] = []
        for index, page in enumerate(document):
            raw_text = page.get_text("text", sort=True)
            text = _normalize_text(raw_text)
            pages.append(PageText(page_number=index + 1, text=text))

        if not any(page.text for page in pages):
            raise PdfReadError(
                f"{file_name}: テキストを抽出できませんでした。"
                "OCRが必要なスキャンPDFはMVP対象外です。"
            )
        return pages
    finally:
        document.close()


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
