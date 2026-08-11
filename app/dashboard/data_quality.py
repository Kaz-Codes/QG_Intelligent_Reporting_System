"""Say what the data cannot support, next to the figure that depends on it.

WHY THIS EXISTS
    Several figures on these dashboards rest on columns that are only partly
    filled. Only 197 of 1,424 logistics orders carry an ETD; 28 of 36 live
    consignments carry a required date. A number derived from 14% of the rows
    looks exactly like a number derived from all of them, and the reader has no
    way to tell which they are looking at.

    So every figure whose basis is incomplete carries a NOTE saying so, in the
    same shape everywhere, and the screen renders it beside the number rather
    than in a footnote nobody reads.

WHAT COUNTS AS WORTH SAYING
    Full coverage is silent — a note on every figure is noise, and noise is
    what stops people reading the notes that matter. `coverage_note` returns
    None at 100%, `info` down to 90%, `warning` below that, and `severe` below
    half, where the figure describes a minority of the records and should be
    read as a sample rather than a total.
"""

INFO = "info"
WARNING = "warning"
SEVERE = "severe"


def _severity(pct):
    if pct >= 100:
        return None
    if pct >= 90:
        return INFO
    if pct >= 50:
        return WARNING
    return SEVERE


def coverage_note(covered, total, subject, column, effect=None):
    """A note about a partly-filled column, or None when it is complete.

    covered / total — how many records carry the value, out of how many.
    subject         — what the records are ("logistics orders").
    column          — the field in business words ("an ETD").
    effect          — what it does to the figure, when that is not obvious.
    """
    if not total or covered >= total:
        return None

    pct = covered / total * 100
    missing = total - covered

    message = (
        f"{covered:,} of {total:,} {subject} ({pct:.1f}%) have {column}"
        f" — {missing:,} cannot be counted here."
    )
    if effect:
        message = f"{message} {effect}"

    return {
        "severity": _severity(pct),
        "message": message,
        "covered": covered,
        "total": total,
        "pct": round(pct, 1),
        "subject": subject,
        "column": column,
    }


def note(severity, message):
    """A plain data note that is not about column coverage."""
    return {
        "severity": severity,
        "message": message,
        "covered": None,
        "total": None,
        "pct": None,
        "subject": None,
        "column": None,
    }


def collect(*notes):
    """Drop the Nones and order worst-first, so the screen leads with the worst.

    A section's notes are the union of its KPIs' notes, which is why this
    tolerates None freely — a caller can pass every candidate note without
    checking each one.
    """
    order = {SEVERE: 0, WARNING: 1, INFO: 2}
    real = [n for n in notes if n]
    real.sort(key=lambda n: order.get(n["severity"], 3))
    return real
