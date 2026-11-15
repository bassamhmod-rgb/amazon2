"""Arabic, paginated PDFs shared by preview, download and printing."""
from functools import lru_cache
from io import BytesIO

import arabic_reshaper
from bidi.algorithm import get_display
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, LongTable, SimpleDocTemplate, Spacer, TableStyle

from .user_handover import REPORT_NOTE, CASH_NOTE, PERMISSIONS_NOTE


@lru_cache(maxsize=1)
def _font():
    pdfmetrics.registerFont(TTFont("HandoverArabic",
        str(settings.BASE_DIR / "static" / "fonts" / "Tahoma.ttf")))
    return "HandoverArabic"


def _visual(text):
    return get_display(arabic_reshaper.reshape(str(text)))


class ArabicText(Flowable):
    """Wrap logical text first, then shape each line so RTL stays in order."""
    def __init__(self, text, size=8):
        super().__init__()
        self.text, self.size, self.lines = str(text), size, []

    def wrap(self, available_width, available_height):
        self.width = max(1, available_width)
        self.lines = []
        for paragraph in self.text.splitlines() or [""]:
            line = ""
            for word in paragraph.split():
                candidate = f"{line} {word}".strip()
                if pdfmetrics.stringWidth(_visual(candidate), _font(), self.size) <= self.width:
                    line = candidate
                    continue
                if line:
                    self.lines.append(line)
                line = ""
                for char in word:
                    if line and pdfmetrics.stringWidth(_visual(line + char), _font(), self.size) > self.width:
                        self.lines.append(line)
                        line = ""
                    line += char
            self.lines.append(line)
        self.height = len(self.lines) * (self.size + 4)
        return self.width, self.height

    def draw(self):
        self.canv.setFont(_font(), self.size)
        for index, line in enumerate(self.lines):
            self.canv.drawRightString(self.width, self.height - self.size - index * (self.size + 4), _visual(line))


def build_handover_pdf(*, title, store_name, period, user_name, headers, rows,
                       paper="a4", orientation="portrait", detailed=False, restricted=False):
    _font()
    page_size = A5 if paper == "a5" else A4
    if orientation == "landscape":
        page_size = landscape(page_size)
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=page_size,
        rightMargin=22, leftMargin=22, topMargin=83, bottomMargin=30,
        title=f"{title} — {store_name}", author=store_name)

    def page_header(canvas, doc):
        canvas.saveState()
        width, height = doc.pagesize
        for text, y, size in ((f"{title} — {store_name}", height-28, 12),
                               (f"{period} • المستخدم: {user_name}", height-48, 9)):
            # Keep a long business/user name inside the sheet.
            shaped = _visual(text)
            text_width = pdfmetrics.stringWidth(shaped, _font(), size)
            canvas.setFont(_font(), min(size, size * (width-44) / max(1, text_width)))
            canvas.drawRightString(width-22, y, shaped)
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.line(22, height-63, width-22, height-63)
        canvas.setFont(_font(), 8)
        canvas.drawCentredString(width/2, 15, str(doc.page))
        canvas.restoreState()

    notes = [REPORT_NOTE, CASH_NOTE]
    if restricted:
        notes.append(PERMISSIONS_NOTE)
    if detailed:
        notes.append("المواد بوحدة الفاتورة وعملتها، قبل حسم الفاتورة. الكمية المجانية لا تزيد المبلغ.")
    if not rows:
        notes.append("لا توجد سجلات ضمن الفترة والمستخدم المحددين.")
    story = []
    for note in notes:
        story.extend([ArabicText(note), Spacer(1, 5)])
    table_rows = [[ArabicText(value, 8) for value in reversed(headers)]]
    table_rows.extend([[ArabicText(value, 8) for value in reversed(row)] for row in rows])
    weights = ([1, 1, 1.3, 3] if len(headers) == 4 else
               [1, 1.3, 2, 2, 1.5, 1.2, 1.4] if len(headers) == 7 else
               [1, 1.3, 1.3, 1.2, 1.2, 1.3, 2.6, 2, 1.7, 1.3])
    widths = [document.width * weight / sum(weights) for weight in weights]
    table = LongTable(table_rows, colWidths=widths, repeatRows=1, hAlign="RIGHT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE5EF")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    document.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return buffer.getvalue()
