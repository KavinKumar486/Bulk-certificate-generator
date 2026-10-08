from types import SimpleNamespace
from pypdf import PdfReader

from app.services.pdf_service import render_certificate


def test_render_certificate_valid(tmp_path):
    cert = SimpleNamespace(
        recipient_name="Asha Rao",
        course="FastAPI 101",
        issue_date="2026-10-01",
    )
    event_name = "PyCon Workshop 2026"
    out_path = tmp_path / "cert.pdf"

    result_path = render_certificate(cert, event_name, out_path)

    # Output file exists and starts with %PDF
    assert result_path.exists()
    with open(result_path, "rb") as f:
        header = f.read(4)
        assert header == b"%PDF"

    # Opens with pypdf, has exactly 1 page
    reader = PdfReader(str(result_path))
    assert len(reader.pages) == 1

    # Extracted text contains recipient name and event name
    page_text = reader.pages[0].extract_text()
    assert "Asha Rao" in page_text
    assert "PyCon Workshop 2026" in page_text
    assert "FastAPI 101" in page_text


def test_render_certificate_missing_optional_fields(tmp_path):
    cert = SimpleNamespace(
        recipient_name="John Doe",
        course=None,
        issue_date=None,
    )
    event_name = "Tech Summit 2026"
    out_path = tmp_path / "cert_minimal.pdf"

    result_path = render_certificate(cert, event_name, out_path)
    assert result_path.exists()

    reader = PdfReader(str(result_path))
    assert len(reader.pages) == 1
    page_text = reader.pages[0].extract_text()
    assert "John Doe" in page_text
    assert "Tech Summit 2026" in page_text


def test_render_certificate_very_long_name(tmp_path):
    long_name = (
        "Wolfeschlegelsteinhausenbergerdorff Welchevor Ensenbonind Vortern "
        "Grafe Augustus Maximilian von Hohenzollern the Third"
    )
    cert = SimpleNamespace(
        recipient_name=long_name,
        course="Super Long Course Description That Might Also Be Quite Long",
        issue_date="2026-10-01",
    )
    event_name = "International Mega Conference on Scalable Architecture 2026"
    out_path = tmp_path / "cert_long.pdf"

    # Should not raise any exception
    result_path = render_certificate(cert, event_name, out_path)
    assert result_path.exists()

    reader = PdfReader(str(result_path))
    assert len(reader.pages) == 1
    page_text = reader.pages[0].extract_text()
    # At least part of the name is preserved and fits
    assert "Wolfeschlegelstein" in page_text


def test_render_certificate_creates_parent_directories(tmp_path):
    cert = SimpleNamespace(recipient_name="Jane Smith", course="", issue_date="")
    nested_path = tmp_path / "deep" / "nested" / "dir" / "cert_nested.pdf"

    assert not nested_path.parent.exists()
    result_path = render_certificate(cert, "Annual Gala", nested_path)

    assert nested_path.parent.exists()
    assert result_path.exists()
