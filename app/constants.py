from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = BASE_DIR / "templates" / "certificate.pdf"

PAGE_WIDTH = 841.89
PAGE_HEIGHT = 595.28

# Field coordinate map matching templates/certificate.pdf
FIELDS = {
    "name": {
        "x": PAGE_WIDTH / 2,
        "y": 352,
        "font_name": "Helvetica-Bold",
        "font_size": 26,
        "alignment": "center",
        "color": "#1A202C",
        "max_width": 500,
        "min_font_size": 12,
    },
    "event_name": {
        "x": PAGE_WIDTH / 2,
        "y": 260,
        "font_name": "Helvetica-Bold",
        "font_size": 20,
        "alignment": "center",
        "color": "#2B6CB0",
        "max_width": 550,
        "min_font_size": 12,
    },
    "course": {
        "x": PAGE_WIDTH / 2,
        "y": 228,
        "font_name": "Helvetica-Oblique",
        "font_size": 14,
        "alignment": "center",
        "color": "#4A5568",
        "max_width": 550,
        "min_font_size": 10,
    },
    "date": {
        "x": 230,
        "y": 148,
        "font_name": "Helvetica",
        "font_size": 11,
        "alignment": "center",
        "color": "#2D3748",
        "max_width": 130,
        "min_font_size": 9,
    },
}
