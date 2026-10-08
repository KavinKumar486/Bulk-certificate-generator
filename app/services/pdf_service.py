import io
from pathlib import Path
from typing import Any
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from app.constants import FIELDS, PAGE_HEIGHT, PAGE_WIDTH, TEMPLATE_PATH


def _draw_text_fitted(
    c: canvas.Canvas,
    text: str,
    field_cfg: dict[str, Any],
) -> None:
    font_name = field_cfg.get("font_name", "Helvetica")
    font_size = field_cfg.get("font_size", 12)
    min_size = field_cfg.get("min_font_size", 8)
    max_w = field_cfg.get("max_width", PAGE_WIDTH - 60)
    x = field_cfg["x"]
    y = field_cfg["y"]
    alignment = field_cfg.get("alignment", "center")
    color = field_cfg.get("color", "#000000")

    c.setFillColor(HexColor(color))

    # Shrink to fit within max width
    current_size = float(font_size)
    while current_size > min_size and c.stringWidth(text, font_name, current_size) > max_w:
        current_size -= 0.5

    # If still too wide at minimum font size, truncate with ellipsis
    rendered_text = text
    if c.stringWidth(rendered_text, font_name, current_size) > max_w:
        while len(rendered_text) > 1 and c.stringWidth(rendered_text + "...", font_name, current_size) > max_w:
            rendered_text = rendered_text[:-1]
        rendered_text = rendered_text + "..."

    c.setFont(font_name, current_size)
    if alignment == "center":
        c.drawCentredString(x, y, rendered_text)
    elif alignment == "right":
        c.drawRightString(x, y, rendered_text)
    else:
        c.drawString(x, y, rendered_text)


def render_certificate(cert: Any, event_name: str, out_path: Path | str) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Certificate template not found at {TEMPLATE_PATH}")

    # Extract field values from cert
    name = getattr(cert, "recipient_name", None) or getattr(cert, "name", None) or ""
    course = getattr(cert, "course", None) or ""
    date_val = getattr(cert, "issue_date", None) or getattr(cert, "date", None) or ""

    values = {
        "name": str(name).strip(),
        "event_name": str(event_name or "").strip(),
        "course": str(course).strip(),
        "date": str(date_val).strip(),
    }

    # 1. Draw in-memory overlay with ReportLab
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    for field_key, field_cfg in FIELDS.items():
        val = values.get(field_key)
        if val:
            _draw_text_fitted(c, val, field_cfg)

    c.showPage()
    c.save()
    packet.seek(0)

    # 2. Merge overlay onto page 1 of template using pypdf
    template_reader = PdfReader(str(TEMPLATE_PATH))
    overlay_reader = PdfReader(packet)

    writer = PdfWriter()
    template_page = template_reader.pages[0]
    overlay_page = overlay_reader.pages[0]
    template_page.merge_page(overlay_page)
    writer.add_page(template_page)

    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path
