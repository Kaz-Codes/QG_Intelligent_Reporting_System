"""
DAYS OF STOCK — one definition, used by every screen that shows it.

This module exists because there were two. The Inventory dashboard divided
stock value by the last TWELVE MONTHS' issuance, while the Overview's Stores
section divided the same stock value by the last NINETY DAYS' — and reported
the answer under a tile captioned "at the last 12 months' usage". The same
warehouse therefore had 81 days of runway on one screen and 54 on the other,
and neither number was wrong for its own formula, which is exactly what makes
that class of bug so expensive: both screens looked right.

THE CANONICAL DEFINITION

    days of stock = stock value on hand / (value issued in the window / days)

  * VALUE, not quantity. A store holds bolts and shafts; summing units is
    meaningless, summing rupees is not.
  * The window is TWELVE MONTHS, which is what the tiles have always claimed.
  * The window ends at the LATEST ISSUANCE IN THE DATA, not today. The issuance
    table is historical; anchoring to today would measure an empty window and
    report every store as having infinite runway.
  * No consumption in the window means no runway to state — `None`, never 0 and
    never "infinite". A store nothing has left in a year is a data question, not
    a store with excellent cover.

Anything that needs days-of-stock imports from here. Do not re-derive it.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, func

from app.loading.schemas.stores_schemas import Issuance

# Twelve months. The Inventory dashboard's own 12-month figures use the same
# constant, so the runway and the "issued in the last 12 months" total it is
# computed from can never describe different windows.
RUNWAY_WINDOW_DAYS = 365


def runway_window(db, window_days=RUNWAY_WINDOW_DAYS):
    """(start, end, days) — the window runway is measured over.

    Anchored on the latest issuance rather than today; see the module docstring.
    Returns (None, None, window_days) when there is no issuance at all, which
    callers must read as "no runway can be stated" rather than as zero usage.
    """
    latest = db.execute(select(func.max(Issuance.from_date))).scalar()
    if latest is None:
        return None, None, window_days
    return latest - timedelta(days=window_days), latest, window_days


def days_of_stock(stock_value, issued_value, window_days=RUNWAY_WINDOW_DAYS):
    """Stock on hand divided by the daily issuance rate, in days."""
    if not window_days or issued_value is None or Decimal(issued_value) <= 0:
        return None
    if stock_value is None or Decimal(stock_value) <= 0:
        return None

    daily = Decimal(issued_value) / Decimal(window_days)
    return round(float(Decimal(stock_value) / daily), 1)


# The one sentence every screen uses to describe the figure, so the wording
# cannot drift apart even where the number cannot.
BASIS = "value issued over the last 12 months, ending at the latest issuance in the data"
