from panel_rag.chunking import chunk_pages
from panel_rag.models import PageText


def test_chunking_preserves_page_and_source_metadata() -> None:
    pages = [PageText(page_number=3, text=("DC24V power supply. " * 80).strip())]

    chunks = chunk_pages(
        pages,
        document_id="doc-1",
        file_name="spec.pdf",
        max_chars=160,
        overlap_chars=30,
    )

    assert len(chunks) > 1
    assert all(item.page_number == 3 for item in chunks)
    assert all(item.file_name == "spec.pdf" for item in chunks)
    assert all(len(item.text) <= 160 for item in chunks)
    assert len({item.chunk_id for item in chunks}) == len(chunks)


def test_chunking_rejects_invalid_overlap() -> None:
    pages = [PageText(page_number=1, text="text")]

    try:
        chunk_pages(
            pages,
            document_id="doc",
            file_name="a.pdf",
            max_chars=100,
            overlap_chars=100,
        )
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")

