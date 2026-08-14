"""The reporting window every dashboard shares.

ONE definition of "the current period", used by imports, purchases, inventory
and the overview, so the same date filter means the same thing everywhere.

THE DEFAULT IS THE CURRENT MONTH. Both bounds omitted -> the 1st of this month
to today; either bound given -> that custom range. The resolved window always
comes back in the payload, so a screen labels its tiles with the range that was
actually computed rather than the one it asked for.

WHY `coverage` EXISTS
    A period figure must never be a bare, unexplained zero. The loaded data does
    not all run to today — purchases currently stop in January while issuance
    runs to this morning — so defaulting to the current month leaves some
    dashboards genuinely empty. "Rs 0" on its own reads as a broken tile, or
    worse, as a real collapse in spend.

    So every dashboard reports, alongside its figures, how much data its source
    actually holds and whether the chosen window found any of it. The front end
    can then say "no purchases in Aug 2026 — latest data is 23 Jan 2026" and
    offer to jump there, instead of showing a confident zero.
"""

from datetime import date, timedelta
from decimal import Decimal

MONTH_TO_DATE = "month_to_date"
CUSTOM = "custom"

#-----------------------------------------------------
# WHICH PROCUREMENT DATE A SCREEN DEFAULTS TO
#
# Purchases carries two real events — when the order was PLACED (`po_date`) and
# when it was actually BOUGHT (`purchase`) — and both are fully populated, so
# the caller picks. But the DEFAULT has to be one value in one place.
#
# It was two. The Overview defaulted to `po_date` while the Purchases dashboard
# defaulted to `purchase`, so the same window showed Rs 7.33bn over 5,036
# orders on one screen and Rs 7.40bn over 5,187 on the other. Neither was
# wrong; they were answering different questions under the same label, and
# nothing on either screen said which.
#
# `purchase` wins because it is what "procurement value this month" is normally
# taken to mean — money spent, not money committed — and because every other
# section of the Overview dates on when something HAPPENED (goods landing,
# stock issuing) rather than when it was promised.
#-----------------------------------------------------

PURCHASES_DATE_DEFAULT = "purchase"

#-----------------------------------------------------
# HOW LONG "NOT MOVING" HAS TO LAST BEFORE STOCK COUNTS AS DEAD
#
# Was two. The Inventory dashboard's Fast/Slow/Dead split has always used a
# fixed 12-month (365-day) issuance window baked into the movement
# classification. The Overview's own dead-stock figure was computed
# separately and defaulted to a 180-day threshold — so the same warehouse
# could read as, say, 700 dead items on one screen and a different count on
# the other, both "correct" for windows nobody had told the reader disagreed.
#
# The Overview's threshold stays a real, user-adjustable query parameter
# (`dead_stock_days`) — that flexibility is worth keeping. What cannot be two
# values is the DEFAULT, so both screens land on the same figure until
# somebody deliberately widens or narrows the Overview's window.
#-----------------------------------------------------

DEAD_STOCK_WINDOW_DAYS = 365

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def resolve_period(date_from=None, date_to=None, today=None):
    """(start, end, kind) — the current month unless a range is given."""
    today = today or date.today()

    if date_from is None and date_to is None:
        return today.replace(day=1), today, MONTH_TO_DATE

    return (date_from or date.min, date_to or today, CUSTOM)


def period_label(start, end, kind):
    """A human label for the window, so the screen never has to guess."""
    if kind == MONTH_TO_DATE:
        return f"{MONTH_NAMES[start.month - 1]} {start.year} to date"

    if start == date.min:
        return f"Up to {end.isoformat()}"

    if start.year == end.year and start.month == end.month:
        if start.day == 1:
            return f"{MONTH_NAMES[start.month - 1]} {start.year}"

    return f"{start.isoformat()} to {end.isoformat()}"


def serialize_period(start, end, kind):
    return {
        "from": start if start != date.min else None,
        "to": end,
        "kind": kind,
        "label": period_label(start, end, kind),
    }


#-----------------------------------------------------
# TREND BUCKETS THAT FIT THE WINDOW
#
# A month-long window bucketed by MONTH is one bar — useless. So the bucket size
# follows the window: a few days across a month, weeks across a quarter, months
# across a year or more.
#
# Empty buckets are always emitted. Leaving a quiet period out draws the line
# straight across it and reads as steady activity through a gap where there was
# none — the chart would be inventing data.
#-----------------------------------------------------

DAY = "day"
WEEK = "week"
MONTH = "month"
QUARTER = "quarter"


def bucket_size(start, end):
    """(kind, days) for the window — 3-day buckets inside a month.

    The top tier exists so a very wide range cannot produce hundreds of bars: a
    2000-2030 window bucketed monthly is 372 of them, nearly all empty, which is
    unreadable and slow to draw.
    """
    span = (end - start).days + 1

    if span <= 45:
        return DAY, 3
    if span <= 120:
        return WEEK, 7
    if span <= 1100:            # up to ~3 years
        return MONTH, 0
    return QUARTER, 0


def _month_start(d):
    return d.replace(day=1)


def _add_month(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def trend_buckets(start, end):
    """[(bucket_start, bucket_end, label), ...] covering the whole window."""
    kind, days = bucket_size(start, end)
    buckets = []

    if kind in (MONTH, QUARTER):
        step = 3 if kind == QUARTER else 1
        # Quarters start on the calendar quarter, so "Q1" always means Jan-Mar
        # rather than wherever the window happened to begin.
        cursor = _month_start(start)
        if kind == QUARTER:
            cursor = cursor.replace(month=((cursor.month - 1) // 3) * 3 + 1)

        while cursor <= end:
            nxt = cursor
            for _ in range(step):
                nxt = _add_month(nxt)

            label = (f"Q{(cursor.month - 1) // 3 + 1} {cursor.year}"
                     if kind == QUARTER
                     else f"{MONTH_NAMES[cursor.month - 1][:3]} {cursor.year}")

            buckets.append((cursor, nxt - timedelta(days=1), label))
            cursor = nxt
        return buckets

    cursor = start
    while cursor <= end:
        last = min(cursor + timedelta(days=days - 1), end)
        # "5–7 Aug" for a multi-day bucket, "5 Aug" when it collapses to one.
        label = (f"{cursor.day}–{last.day} {MONTH_NAMES[last.month - 1][:3]}"
                 if last != cursor
                 else f"{cursor.day} {MONTH_NAMES[cursor.month - 1][:3]}")
        buckets.append((cursor, last, label))
        cursor = last + timedelta(days=1)

    return buckets


def build_trend(start, end, dated_values):
    """Bucket (date, amount) pairs across the window.

    `dated_values` is an iterable of (date, Decimal). Anything with no date is
    the caller's to report — it belongs in no bucket and must not be silently
    dropped into the first one.
    """
    buckets = trend_buckets(start, end)
    totals = {b[0]: Decimal("0") for b in buckets}
    counts = {b[0]: 0 for b in buckets}

    edges = [b[0] for b in buckets]

    for when, amount in dated_values:
        if when is None or when < start or when > end:
            continue
        # Last edge at or before `when`.
        placed = None
        for edge in edges:
            if edge <= when:
                placed = edge
            else:
                break
        if placed is not None:
            totals[placed] += amount or Decimal("0")
            counts[placed] += 1

    kind, days = bucket_size(start, end)

    return {
        "granularity": kind,
        "bucket_days": days,
        "points": [
            {
                "bucket": b[0].isoformat(),
                "label": b[2],
                "value": totals[b[0]],
                "count": counts[b[0]],
            }
            for b in buckets
        ],
    }


def coverage(earliest, latest, rows_in_period, total_rows, date_field):
    """What the SOURCE holds, next to what the WINDOW found.

    `date_field` is named so a reader knows which date the window was applied
    to — "no purchases in this period" means something different depending on
    whether the period filtered the purchase date or the PO date.
    """
    return {
        "date_field": date_field,
        "earliest": earliest,
        "latest": latest,
        "rows_in_period": rows_in_period,
        "rows_total": total_rows,
        "is_empty": rows_in_period == 0,
        # The month the front end should offer as "jump to the latest data".
        "latest_month": latest.replace(day=1) if latest else None,
    }
