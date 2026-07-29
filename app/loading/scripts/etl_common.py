import re
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
