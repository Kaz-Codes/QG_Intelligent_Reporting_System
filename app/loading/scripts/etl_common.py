import re
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values

# Values that mean "no data" in the workbook
PLACEHOLDERS = {"-", "--", "---", "", "n/a", "na", "nil", "none", "tbd"}


# ---------------------------------------------------------------------------
# Key cleaning
# ---------------------------------------------------------------------------

_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b", re.IGNORECASE)

def clean_key(value) -> str | None:
    """Normalize an Exp # / Batch # value.
    '2360th' -> '2360' ; ' 25-018TH ' -> '25-018' ; '-' -> None
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if s.lower() in PLACEHOLDERS:
        return None
    s = _ORDINAL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s.upper() if s else None


def make_export_key(exp_no, batch_no):
    """(exp_no, batch_no) tuple used to look up export_id. batch '' if none."""
    e = clean_key(exp_no)
    b = clean_key(batch_no) or ""
    return (e, b) if e else None


# ---------------------------------------------------------------------------
# Value cleaning
# ---------------------------------------------------------------------------

def clean_text(value):
    """Trim text; placeholders -> None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return None if s.lower() in PLACEHOLDERS else s


def clean_status(value):
    """Like clean_text but keeps 'Pending' (a real status value)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if s.lower() in PLACEHOLDERS:
        return None
    return s


def clean_number(value):
    """Extract a numeric value. '1 Nos.' -> 1.0 ; 'Rs. 12,500' -> 12500 ; '-' -> None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").strip()
    if s.lower() in PLACEHOLDERS:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def clean_int(value):
    n = clean_number(value)
    return int(n) if n is not None else None


def clean_date(value):
    """Coerce Excel datetimes / date strings to date; anything else -> None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        if value.strip().lower() in PLACEHOLDERS:
            return None

        # Remove any HTML that follows the date
        value = value.split("<", 1)[0].strip()

    ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(ts) else ts.date()


# Excel keeps dates as a day count from 1899-12-30. When a column mixes real
# dates with those raw numbers, pandas gives up and hands the number back
# untouched — and pd.to_datetime would then read 46026 as 46026 NANOSECONDS,
# quietly producing 1970-01-01 instead of a 2026 date.
_EXCEL_EPOCH = "1899-12-30"
_SERIAL_MIN = 20000   # 1954-10-03 — below this it is a quantity, not a date
_SERIAL_MAX = 60000   # 2064-04-05 — above this it is an amount, not a date


def clean_date_any(value):
    """clean_date, but also decodes bare Excel day-serials (46026 -> 2026-01-05).

    Use for any column the workbook stores as a mix of real dates and serials
    (e.g. 'ETA Works / ETA Destination' on the shifting sheet). A number
    outside the plausible serial window is treated as not-a-date rather than
    being coerced into one.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)) and _SERIAL_MIN <= float(value) <= _SERIAL_MAX:
        ts = pd.to_datetime(float(value), unit="D", origin=_EXCEL_EPOCH, errors="coerce")
        return None if pd.isna(ts) else ts.date()

    # A serial that arrived as text ("46026") is still a serial.
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit() and _SERIAL_MIN <= int(s) <= _SERIAL_MAX:
            ts = pd.to_datetime(int(s), unit="D", origin=_EXCEL_EPOCH, errors="coerce")
            return None if pd.isna(ts) else ts.date()

    return clean_date(value)


def parse_qty_uom(value):
    """'1 Nos.' -> (1.0, 'Nos.') ; 5 -> (5.0, None)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    s = str(value).strip()
    if s.lower() in PLACEHOLDERS:
        return None, None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*(.*)", s)
    if not m:
        return None, s or None
    qty = float(m.group(1))
    uom = m.group(2).strip() or None
    return qty, uom


def load_export_map(conn) -> dict:
    """Return {(exp_no, batch_no): export_id} for FK resolution."""
    with conn.cursor() as cur:
        cur.execute("SELECT exp_no, batch_no, export_id FROM exports")
        return {(e, b): i for e, b, i in cur.fetchall()}


def bulk_insert(conn, table, columns, rows, conflict_clause=""):
    """Insert many rows with execute_values. rows = list of tuples."""
    if not rows:
        print(f"  {table}: nothing to insert")
        return
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s {conflict_clause}"
    )
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=500)
    conn.commit()
    print(f"  {table}: inserted {len(rows)} rows")


def read_sheet(sheet_name, file_path) -> pd.DataFrame:
    """Read one worksheet with the header on the first row."""
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df.columns = df.columns.str.strip()
    df.columns = df.columns.str.replace("\n", " ", regex=False)
    df.columns = df.columns.str.replace(r"\s+", " ", regex=True)
    df = df.dropna(how="all")
    print(f"Read '{sheet_name}': {len(df)} rows, {len(df.columns)} columns")
    return df


def list_excel_files(directory) -> list:
    """Every Excel workbook in a folder, sorted by name, skipping Excel's own
    ~$ lock files and anything that is not a workbook.

    Loaders read ALL of these and concatenate them, so loading another period's
    data is just a matter of dropping its file into the folder — no code change.
    The sort makes the order deterministic, which matters where row identity is
    derived from position (the logistics packing sheet).
    """
    directory = Path(directory)
    files = sorted(
        f for f in directory.iterdir()
        if f.is_file()
        and f.suffix.lower() in (".xlsx", ".xls")
        and not f.name.startswith("~$")
    )
    if not files:
        raise FileNotFoundError(f"No Excel files found in {directory}")
    return files


def read_and_concat(sheet_name, files) -> pd.DataFrame:
    """Read the same sheet from every file and stack them into one DataFrame.

    The index is reset so it is a clean 0..N range across all files (a loader
    that keys off the row index must account for that; the simple column loaders
    do not use the index at all).
    """
    frames = [read_sheet(sheet_name, f) for f in files]
    return pd.concat(frames, ignore_index=True)
