from io import BytesIO
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font

#-----------------------------------------------------
# EXCEL EXPORT
#
# Shared by every module's export endpoint. The route builds the header row
# and one list of cells per record; this turns that into an .xlsx download.
# The export always runs on the SAME filtered queryset the list view uses, so
# what you see is what you export — the route reuses fetch_consignments_page
# with no page limit rather than a second, drifting query.
#-----------------------------------------------------

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cell(value):
    # openpyxl accepts str / number / date / datetime. Everything else
    # (Decimal, Enum, None) is coerced to something it can write.
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, date, datetime, bool)):
        return value
    return str(value)


def xlsx_response(filename, headers, rows, sheet_title="Export"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        ws.append([_cell(v) for v in row])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
