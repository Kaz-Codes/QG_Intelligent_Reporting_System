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
    if isinstance(value, datetime) and value.tzinfo is not None:
        # EXCEL HAS NO CONCEPT OF A TIMEZONE, and openpyxl raises rather than
        # dropping one: "Excel does not support timezones in datetimes."
        #
        # Every timestamp in this app is `DateTime(timezone=True)`, so any
        # export that adds a timestamp COLUMN hits this - the imports export
        # did, the first time it carried `created_at` and the landed-cost
        # audit times, and it surfaced as a 500 on the whole download rather
        # than as a bad cell. Converted here, once, rather than in each route:
        # the next export to add a timestamp should not have to rediscover it.
        #
        # Converted to LOCAL time, not stripped: dropping the tzinfo off a UTC
        # value would silently shift every timestamp by the offset and the
        # sheet would look fine.
        return value.astimezone().replace(tzinfo=None)
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
