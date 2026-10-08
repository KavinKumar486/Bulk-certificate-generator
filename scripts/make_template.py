from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


def create_certificate_template(output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = landscape(A4)
    c = canvas.Canvas(str(output_path), pagesize=landscape(A4))

    # Background tint / borders
    c.setStrokeColor(HexColor("#1A365D"))  # Deep navy
    c.setLineWidth(4)
    c.rect(25, 25, width - 50, height - 50)

    c.setStrokeColor(HexColor("#C59B27"))  # Gold accent
    c.setLineWidth(1.5)
    c.rect(32, 32, width - 64, height - 64)

    # Corner decorations (small geometric accents)
    c.setFillColor(HexColor("#C59B27"))
    c.circle(32, 32, 3, fill=1, stroke=0)
    c.circle(width - 32, 32, 3, fill=1, stroke=0)
    c.circle(32, height - 32, 3, fill=1, stroke=0)
    c.circle(width - 32, height - 32, 3, fill=1, stroke=0)

    # Heading
    c.setFillColor(HexColor("#1A365D"))
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(width / 2, 470, "CERTIFICATE OF COMPLETION")

    # Presentation text
    c.setFillColor(HexColor("#4A5568"))
    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, 415, "THIS IS PROUDLY PRESENTED TO")

    # Name underline
    c.setStrokeColor(HexColor("#CBD5E0"))
    c.setLineWidth(1)
    c.line(width / 2 - 200, 340, width / 2 + 200, 340)

    # Description text
    c.setFillColor(HexColor("#4A5568"))
    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, 295, "for participating and successfully completing")

    # Bottom layout: Date & Signature lines
    # Date line
    c.setStrokeColor(HexColor("#A0AEC0"))
    c.setLineWidth(1)
    c.line(160, 140, 300, 140)
    c.setFillColor(HexColor("#718096"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(230, 124, "DATE")

    # Signature line
    c.line(540, 140, 680, 140)
    c.drawCentredString(610, 124, "AUTHORIZED SIGNATURE")

    # Decorative signature placeholder
    c.setFillColor(HexColor("#2B6CB0"))
    c.setFont("Times-Italic", 18)
    c.drawCentredString(610, 148, "Program Director")

    c.showPage()
    c.save()


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "templates" / "certificate.pdf"
    create_certificate_template(target)
    print(f"Generated template at: {target}")
