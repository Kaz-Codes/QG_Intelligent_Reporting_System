"""
WHICH RECORDS IS AN OVERVIEW FIGURE ABOUT?

The overview's rule is that it never materializes rows — every figure on it is a
single SQL aggregate, which is what lets it span ~49k issuance rows and still
answer instantly. These functions do not break that rule: each is its own
single page of an `ORDER BY ... OFFSET ... LIMIT`, so the biggest thing that
ever crosses into Python is one page, whatever the table underneath holds.

They exist because a cross-module rollup is the figure a user is LEAST able to
check. "Rs 262m of imports this month" spans four modules and two valuation
bases; without a way to see the consignments behind it there is nowhere to go
but to disbelieve it. Each list is ranked by the quantity that built the figure
(value, freight, lateness) so the records that move it most are at the top.

The shape is the front end's shared ReferenceItem: {id, reference, detail, meta,
badge} — the same list component every module dashboard already opens.
"""

from datetime import timedelta

from sqlalchemy import select, func, or_, desc

from app.imports.models import Consignment, ConsignmentItem
from app.logistics.models import LogisticsConsignment
from app.trucking.models import TruckingConsignment
from app.loading.schemas.stores_schemas import Stock, Issuance, PurchasesData
from app.masters.models import Branch, Supplier
from app.reports.helpers import SHAFT_ITEMS

from app.dashboard.references import clamp, paginate, sql_search_clause
from app.enums import Status
from app.dashboard.whole.helpers import (
    CONSIGNMENT_VALUE, TERMINAL_STATUSES, shaft_consignment_ids,
    purchases_date_column,
    TRUCKING_DATE_FIELDS, LOGISTICS_DATE_DEFAULT,
    _live_consignments, dead_item_ids,
    _imports_window_membership,
)

# These lists are COMPLETE — `total` is always the true count and the caller can
# page all the way through it. Only one page is fetched per request, in SQL, so
# a figure standing over 8,731 orders costs the same as one standing over 3.
# See app/dashboard/references for the contract.


def _money(amount):
    value = float(amount or 0)
    if abs(value) >= 1_000_000_000:
        return f"Rs {value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"Rs {value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"Rs {value / 1_000:.0f}K"
    return f"Rs {value:,.0f}"


def _joined(*parts):
    return " · ".join(part for part in parts if part) or None


def _set(total, items, page, page_size, unit="record"):
    """The reference-set shape, for a page already fetched from the database."""
    return paginate(items, page, page_size, total=total or 0, unit=unit)


#-------------------------------------
# IMPORTS
#-------------------------------------

def _consignment_query():
    """Header + the two master names, valued the same way the tiles are.

    Outer-joined to the masters because a consignment may legitimately carry
    neither — an inner join would quietly shorten the list below the count
    printed on the tile.
    """
    return (
        select(
            Consignment.id,
            Consignment.instrument_number,
            Consignment.current_status,
            Supplier.name,
            Branch.name,
            CONSIGNMENT_VALUE.label("value"),
        )
        .select_from(Consignment)
        .outerjoin(Supplier, Supplier.id == Consignment.supplier_id)
        .outerjoin(Branch, Branch.id == Consignment.branch_id)
        .where(_live_consignments())
    )


def _consignment_rows(db, query, total, page, page_size, badge_value=True):
    page, size = clamp(page, page_size)
    rows = db.execute(
        query.order_by(desc("value"), Consignment.id)
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": cid,
            "reference": instrument or f"IMP-{cid}",
            "detail": status,
            "meta": _joined(supplier, branch),
            "badge": _money(value) if badge_value else status,
        }
        for cid, instrument, status, supplier, branch, value in rows
    ], page, size)


def imports_value_references(db, date_from, date_to, date_field=None,
                             shafts_only=False, page=None, page_size=None,
                             search=None):
    """The consignments inside the imports window, biggest value first.

    `shafts_only` is NOT optional decoration: without it the Shafts tab showed a
    tile reading 1 consignment over a list of 7, because the tile was filtered
    and its list was not.
    """
    # MEMBERSHIP is by line (any line dated inside the window, header
    # fallback), exactly as the tile is (helpers.imports_period_value /
    # _imports_window_membership) — otherwise the list would hand back a
    # different set of consignments than the ones the tile's total was built
    # from. Every line of a qualifying consignment is still shown (never
    # hidden), just not gated by each line's OWN date the way this used to be.
    conditions = [_imports_window_membership(date_field, date_from, date_to)]
    if shafts_only:
        conditions.append(Consignment.id.in_(shaft_consignment_ids()))

    return consignment_line_rows(db, conditions, page, page_size, search)


def imports_in_process_references(db, date_from=None, date_to=None, date_field=None,
                                  shafts_only=False, page=None, page_size=None,
                                  search=None):
    """Everything not yet at a terminal status — the "In Process" tile.

    Windowed like the tile it belongs to, so the list and the count it opens
    from describe the same set.
    """
    conditions = [Consignment.current_status.notin_(TERMINAL_STATUSES)]
    if date_from is not None and date_to is not None:
        conditions.append(_imports_window_membership(date_field, date_from, date_to))
    if shafts_only:
        conditions.append(Consignment.id.in_(shaft_consignment_ids()))

    return consignment_line_rows(db, conditions, page, page_size, search)


def shaft_references(db, arrived, page=None, page_size=None, search=None):
    """Shaft consignments, split the same way the two shaft tiles are."""
    ids = shaft_consignment_ids()
    status = (Consignment.current_status.in_(TERMINAL_STATUSES) if arrived
              else Consignment.current_status.notin_(TERMINAL_STATUSES))

    return consignment_line_rows(
        db, [Consignment.id.in_(ids), status], page, page_size, search
    )


#-------------------------------------
# LOCAL PROCUREMENT
#
# One PO is many rows in `purchases_data`, so everything here groups by PO
# number first — the same correction procurement_period_totals makes. Listing
# the raw rows would show one order five times and contradict the count on the
# tile it opened from.
#-------------------------------------

def _po_search_ids(search):
    """PO numbers with at least one line matching `search`, or None.

    A subquery rather than a plain WHERE on the grouped query: `_po_select`
    aggregates every line of a PO into one row (summed value, joined item
    list), and filtering the raw LINES before that GROUP BY would silently
    shrink the aggregate to just the matching lines — the badge would show
    less than the order is actually worth. Matching the PO number here and
    filtering the grouped query by membership keeps every matched order whole.
    """
    clause = sql_search_clause(
        search, PurchasesData.po_number, PurchasesData.supplier,
        PurchasesData.branch, PurchasesData.item_name,
    )
    if clause is None:
        return None
    return (
        select(PurchasesData.po_number).where(clause).distinct().scalar_subquery()
    )


def _po_rows(db, query, total, page, page_size):
    page, size = clamp(page, page_size)
    rows = db.execute(query.offset((page - 1) * size).limit(size)).all()

    return _set(total, [
        {
            "id": po or f"row-{index}",
            "reference": po or "(no PO)",
            "detail": items,
            "meta": _joined(supplier, branch),
            "badge": _money(amount),
        }
        for index, (po, supplier, branch, items, amount) in enumerate(rows)
    ], page, size)


def _po_select(date_column, date_from, date_to):
    return (
        select(
            PurchasesData.po_number,
            func.min(PurchasesData.supplier),
            func.min(PurchasesData.branch),
            func.string_agg(func.distinct(PurchasesData.item_name), ", "),
            func.coalesce(func.sum(PurchasesData.amount), 0).label("value"),
        )
        .where(date_column.between(date_from, date_to))
        .group_by(PurchasesData.po_number)
        .order_by(desc("value"))
    )


def procurement_value_references(db, date_from, date_to, date_field=None,
                                 page=None, page_size=None, search=None):
    column = purchases_date_column(date_field)
    conditions = [column.between(date_from, date_to)]
    matched = _po_search_ids(search)
    if matched is not None:
        conditions.append(PurchasesData.po_number.in_(matched))

    total = db.execute(
        select(func.count(func.distinct(PurchasesData.po_number)))
        .where(*conditions)
    ).scalar()

    query = _po_select(column, date_from, date_to)
    if matched is not None:
        query = query.where(PurchasesData.po_number.in_(matched))
    return _po_rows(db, query, total, page, page_size)


def procurement_delay_references(db, date_from, date_to, date_field=None,
                                 page=None, page_size=None, search=None):
    """The POs the delay rate counted as late — purchased after they were needed."""
    column = purchases_date_column(date_field)
    late = PurchasesData.required_d < PurchasesData.purchase
    matched = _po_search_ids(search)

    total_conditions = [
        column.between(date_from, date_to),
        PurchasesData.required_d.isnot(None),
        late,
    ]
    if matched is not None:
        total_conditions.append(PurchasesData.po_number.in_(matched))

    total = db.execute(
        select(func.count(func.distinct(PurchasesData.po_number)))
        .where(*total_conditions)
    ).scalar()

    query = (
        _po_select(column, date_from, date_to)
        .where(PurchasesData.required_d.isnot(None))
        .where(late)
    )
    if matched is not None:
        query = query.where(PurchasesData.po_number.in_(matched))
    return _po_rows(db, query, total, page, page_size)


#-------------------------------------
# LOGISTICS / TRUCKING
#-------------------------------------

def trucking_cost_references(db, date_from, date_to, date_field=None, movement=None,
                             page=None, page_size=None, search=None):
    """Trucking jobs by freight, optionally one movement type.

    `movement=None` means the total tile; a movement string narrows to that
    bucket's own tile. Passing the sentinel `"Unclassified"` selects the NULL
    group, which the overview reports as a bucket rather than hiding.
    """
    column = TRUCKING_DATE_FIELDS.get(date_field or LOGISTICS_DATE_DEFAULT,
                                      TRUCKING_DATE_FIELDS[LOGISTICS_DATE_DEFAULT])
    freight = func.coalesce(TruckingConsignment.actual_freight,
                            TruckingConsignment.quoted_freight, 0)

    conditions = [TruckingConsignment.is_deleted.is_(False)]
    if date_from is not None and date_to is not None:
        conditions.append(column.between(date_from, date_to))
    if movement == "Unclassified":
        conditions.append(TruckingConsignment.movement_type.is_(None))
    elif movement:
        conditions.append(TruckingConsignment.movement_type == movement)

    clause = sql_search_clause(
        search, TruckingConsignment.reference_no, TruckingConsignment.source,
        TruckingConsignment.source_ref, TruckingConsignment.movement_type,
        TruckingConsignment.transporter_name,
    )
    if clause is not None:
        conditions.append(clause)

    total = db.execute(
        select(func.count(TruckingConsignment.id)).where(*conditions)
    ).scalar()

    page, size = clamp(page, page_size)
    rows = db.execute(
        select(
            TruckingConsignment.id,
            TruckingConsignment.reference_no,
            TruckingConsignment.source,
            TruckingConsignment.source_ref,
            TruckingConsignment.movement_type,
            TruckingConsignment.transporter_name,
            freight.label("value"),
        )
        .where(*conditions)
        .order_by(desc("value"), TruckingConsignment.id)
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": jid,
            "reference": reference or f"TRK-{jid}",
            "detail": movement_type or "Unclassified",
            "meta": _joined(transporter, source, source_ref),
            "badge": _money(value),
        }
        for jid, reference, source, source_ref, movement_type, transporter, value in rows
    ], page, size)


def shipments_handled_references(db, date_from, date_to, date_field=None,
                                 page=None, page_size=None, search=None):
    """The export ORDERS counted as shipments handled.

    Only the logistics half: the import half is the same consignments
    `imports_value_references` already lists, and a list mixing the two would
    show a consignment twice under one figure.
    """
    from app.dashboard.whole.helpers import LOGISTICS_ORDER_DATE_FIELDS

    column = LOGISTICS_ORDER_DATE_FIELDS.get(
        date_field or LOGISTICS_DATE_DEFAULT,
        LOGISTICS_ORDER_DATE_FIELDS[LOGISTICS_DATE_DEFAULT],
    )
    conditions = [LogisticsConsignment.is_deleted.is_(False),
                  column.between(date_from, date_to)]

    clause = sql_search_clause(
        search, LogisticsConsignment.mo_no, LogisticsConsignment.customer_name,
        LogisticsConsignment.order_type, LogisticsConsignment.current_status,
    )
    if clause is not None:
        conditions.append(clause)

    total = db.execute(
        select(func.count(LogisticsConsignment.id)).where(*conditions)
    ).scalar()

    page, size = clamp(page, page_size)
    rows = db.execute(
        select(
            LogisticsConsignment.id,
            LogisticsConsignment.mo_no,
            LogisticsConsignment.customer_name,
            LogisticsConsignment.order_type,
            LogisticsConsignment.current_status,
        )
        .where(*conditions)
        .order_by(LogisticsConsignment.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": oid,
            "reference": mo or f"LOG-{oid}",
            "detail": customer,
            "meta": _joined(order_type, status),
            "badge": status,
        }
        for oid, mo, customer, order_type, status in rows
    ], page, size)


#-------------------------------------
# STORES
#
# Stock is held per (item, branch); these fold onto the ITEM, matching how the
# inventory dashboard counts, so "4,762 items" means the same thing on both
# screens.
#-------------------------------------

def _stock_rows(db, conditions, total, page, page_size, search=None):
    page, size = clamp(page, page_size)

    clause = sql_search_clause(search, Stock.item_code, Stock.item_name)
    if clause is not None:
        conditions = list(conditions) + [clause]
        # `total` was counted before search narrowed the set — recount rather
        # than trust the caller's figure, which was computed for the
        # unfiltered tile.
        total = db.execute(
            select(func.count(func.distinct(Stock.item_code))).where(*conditions)
        ).scalar()

    rows = db.execute(
        select(
            Stock.item_code,
            func.min(Stock.item_name),
            func.count(func.distinct(Stock.branch)),
            func.coalesce(func.sum(Stock.stock_qty_amount), 0).label("value"),
        )
        .where(*conditions)
        .group_by(Stock.item_code)
        .order_by(desc("value"), Stock.item_code)
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": code,
            "reference": code or "(no code)",
            "detail": name,
            "meta": f"{branches} store{'' if branches == 1 else 's'}",
            "badge": _money(value),
        }
        for code, name, branches, value in rows
    ], page, size)


def stock_value_references(db, page=None, page_size=None, search=None):
    conditions = [Stock.item_code.isnot(None)]
    total = db.execute(
        select(func.count(func.distinct(Stock.item_code))).where(*conditions)
    ).scalar()
    return _stock_rows(db, conditions, total, page, page_size, search)


def dead_stock_references(db, threshold_days, page=None, page_size=None, search=None):
    """The items behind the dead-stock value.

    Same definition as helpers.dead_stock — built on the identical
    helpers.dead_item_ids subquery, so the tile and this list can never
    disagree about which items are dead (they used to: this used to filter
    RAW per-branch stock rows rather than the folded, purchase-aware set the
    tile actually counts).
    """
    latest = db.execute(select(func.max(Issuance.from_date))).scalar()
    if latest is None:
        return paginate([], page, page_size)

    cutoff = latest - timedelta(days=threshold_days)
    dead = dead_item_ids(db, cutoff)

    conditions = [Stock.item_code.in_(select(dead.c.item_code))]
    total = db.execute(
        select(func.count(func.distinct(Stock.item_code))).where(*conditions)
    ).scalar()
    return _stock_rows(db, conditions, total, page, page_size, search)


def imports_status_references(db, bucket, date_from=None, date_to=None,
                              date_field=None, shafts_only=False,
                              page=None, page_size=None, search=None):
    """The consignments in one terminal bucket — "arrived" or "cancelled".

    Two buckets rather than one "closed" list, because an arrival is work
    completed and a cancellation is work abandoned; a reader chasing one does
    not want the other in the list.
    """
    status = (Status.ARRIVED_AT_WORKS.value if bucket == "arrived"
              else Status.ORDER_CANCELLED.value)

    conditions = [Consignment.current_status == status]
    if date_from is not None and date_to is not None:
        conditions.append(_imports_window_membership(date_field, date_from, date_to))
    if shafts_only:
        conditions.append(Consignment.id.in_(shaft_consignment_ids()))

    return consignment_line_rows(db, conditions, page, page_size, search)


def imports_delayed_references(db, date_from=None, date_to=None, date_field=None,
                               shafts_only=False, page=None, page_size=None,
                               search=None):
    """The late consignments, badged with how late — worst first.

    Ranked by lateness rather than value, because that is what the tile counts.
    Same grace period as everywhere else (imports.calculations.DELAY_GRACE_DAYS),
    imported rather than restated.
    """
    from app.dashboard.imports.calculations import DELAY_GRACE_DAYS

    days_late = (Consignment.eta_works - Consignment.required_date)
    conditions = [
        Consignment.required_date.isnot(None),
        Consignment.eta_works.isnot(None),
        days_late > DELAY_GRACE_DAYS,
    ]
    if date_from is not None and date_to is not None:
        conditions.append(_imports_window_membership(date_field, date_from, date_to))
    if shafts_only:
        conditions.append(Consignment.id.in_(shaft_consignment_ids()))

    clause = sql_search_clause(search, Consignment.instrument_number,
                               Supplier.name, Branch.name)
    if clause is not None:
        conditions.append(clause)

    total = db.execute(
        select(func.count(Consignment.id))
        .select_from(Consignment)
        .outerjoin(Supplier, Supplier.id == Consignment.supplier_id)
        .outerjoin(Branch, Branch.id == Consignment.branch_id)
        .where(_live_consignments()).where(*conditions)
    ).scalar()

    page, size = clamp(page, page_size)
    rows = db.execute(
        select(
            Consignment.id, Consignment.instrument_number,
            Supplier.name, Branch.name, days_late.label("days"),
        )
        .select_from(Consignment)
        .outerjoin(Supplier, Supplier.id == Consignment.supplier_id)
        .outerjoin(Branch, Branch.id == Consignment.branch_id)
        .where(_live_consignments()).where(*conditions)
        .order_by(desc("days"), Consignment.id)
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": cid,
            "reference": instrument or f"IMP-{cid}",
            "detail": f"{days} days late",
            "meta": _joined(supplier, branch),
            "badge": f"{days} days late",
        }
        for cid, instrument, supplier, branch, days in rows
    ], page, size, unit="consignment")


def issuance_references(db, date_from, date_to, page=None, page_size=None, search=None):
    """What was issued in the window, folded ONTO THE ITEM CODE.

    Grouped rather than listed line by line: 1,815 issuance lines this month
    stand over 633 items, and "which items did we issue" is the question the
    tile raises. The quantity travels with the value because an issuance is a
    physical movement — how much left the store is half the answer.
    """
    conditions = [Issuance.from_date.between(date_from, date_to),
                  Issuance.item_code.isnot(None)]

    clause = sql_search_clause(search, Issuance.item_code, Issuance.item_name)
    if clause is not None:
        conditions.append(clause)

    total = db.execute(
        select(func.count(func.distinct(Issuance.item_code))).where(*conditions)
    ).scalar()

    page, size = clamp(page, page_size)
    rows = db.execute(
        select(
            Issuance.item_code,
            func.min(Issuance.item_name),
            func.coalesce(func.sum(Issuance.quantity), 0),
            func.count(Issuance.id),
            func.coalesce(func.sum(Issuance.total_price), 0).label("value"),
        )
        .where(*conditions)
        .group_by(Issuance.item_code)
        .order_by(desc("value"), Issuance.item_code)
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": code,
            "reference": code,
            "detail": name,
            "meta": f"{_qty(quantity)} issued over {lines} line{'' if lines == 1 else 's'}",
            "badge": _money(value),
        }
        for code, name, quantity, lines, value in rows
    ], page, size)


def _qty(value):
    """Quantities are stored to 3 decimals; 12.000 should read as 12."""
    number = float(value or 0)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.3f}".rstrip("0").rstrip(".")


#-------------------------------------
# CONSIGNMENT LISTS SHOW THEIR LINES
#
# Same rule as the Imports dashboard: a list never hides lines. The tiles count
# consignments; the list shows the item rows underneath, each with its own
# arrival date and value, and reports both counts so the two reconcile.
#-------------------------------------

def _line_query(conditions):
    return (
        select(
            ConsignmentItem.id,
            Consignment.id.label("consignment_id"),
            Consignment.instrument_number,
            ConsignmentItem.item_name,
            ConsignmentItem.quantity,
            ConsignmentItem.unit_of_measurement,
            func.coalesce(ConsignmentItem.eta_works, Consignment.eta_works).label("line_eta"),
            Supplier.name,
            Branch.name,
            (ConsignmentItem.quantity * ConsignmentItem.unit_price
             * Consignment.exchange_rate).label("value"),
        )
        .select_from(ConsignmentItem)
        .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
        .outerjoin(Supplier, Supplier.id == Consignment.supplier_id)
        .outerjoin(Branch, Branch.id == Consignment.branch_id)
        .where(ConsignmentItem.is_deleted.is_(False))
        .where(_live_consignments())
        .where(*conditions)
    )


def consignment_line_rows(db, conditions, page, page_size, search=None):
    """One page of item LINES, with the consignment count alongside.

    Search matches at the LINE, not the consignment: a line is shown because
    it itself matched, consistent with the rule that a line list never stands
    in for its parent — see the module docstring.
    """
    page, size = clamp(page, page_size)

    clause = sql_search_clause(
        search, Consignment.instrument_number, Supplier.name, Branch.name,
        ConsignmentItem.item_name, Consignment.current_status,
    )
    search_conditions = list(conditions) + ([clause] if clause is not None else [])

    total, groups = db.execute(
        select(func.count(ConsignmentItem.id),
               func.count(func.distinct(ConsignmentItem.consignment_id)))
        .select_from(ConsignmentItem)
        .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
        .outerjoin(Supplier, Supplier.id == Consignment.supplier_id)
        .outerjoin(Branch, Branch.id == Consignment.branch_id)
        .where(ConsignmentItem.is_deleted.is_(False))
        .where(_live_consignments())
        .where(*search_conditions)
    ).one()

    rows = db.execute(
        _line_query(search_conditions)
        .order_by(desc("value"), ConsignmentItem.id)
        .offset((page - 1) * size).limit(size)
    ).all()

    def measure(quantity, unit):
        if quantity is None:
            return None
        number = f"{float(quantity):,.3f}".rstrip("0").rstrip(".")
        return f"{number} {unit or ''}".strip()

    items = [
        {
            "id": f"line-{line_id}",
            "reference": instrument or f"IMP-{cid}",
            "detail": name,
            "meta": " · ".join(part for part in (
                measure(quantity, unit),
                f"ETA {eta}" if eta else "no ETA",
                supplier,
            ) if part),
            "badge": _money(value),
        }
        for line_id, cid, instrument, name, quantity, unit, eta, supplier, branch, value in rows
    ]

    return paginate(items, page, size, total=total or 0,
                    unit="line", groups=groups or 0, group_unit="consignment")


def order_type_references(db, order_type, date_from, date_to, date_field=None,
                          undated=False, all_time=False, page=None, page_size=None,
                          search=None):
    """Logistics orders of one type, in the window — or the undated ones.

    `undated=True` returns the orders carrying NO date in the chosen column,
    whatever their type. They are in no period, which is exactly why they need
    a list of their own: not one local order has a business date, so the local
    tile would otherwise be a zero with nothing behind it.
    """
    from app.dashboard.whole.helpers import LOGISTICS_ORDER_DATE_FIELDS

    column = LOGISTICS_ORDER_DATE_FIELDS.get(
        date_field or LOGISTICS_DATE_DEFAULT,
        LOGISTICS_ORDER_DATE_FIELDS[LOGISTICS_DATE_DEFAULT],
    )

    conditions = [LogisticsConsignment.is_deleted.is_(False)]
    if undated:
        conditions.append(column.is_(None))
    elif all_time:
        # No window at all — for a type that carries no date and so could
        # never appear in one.
        conditions.append(LogisticsConsignment.order_type == order_type)
    else:
        conditions.append(column.between(date_from, date_to))
        conditions.append(LogisticsConsignment.order_type == order_type)

    clause = sql_search_clause(
        search, LogisticsConsignment.mo_no, LogisticsConsignment.customer_name,
        LogisticsConsignment.order_type, LogisticsConsignment.current_status,
    )
    if clause is not None:
        conditions.append(clause)

    total = db.execute(
        select(func.count(LogisticsConsignment.id)).where(*conditions)
    ).scalar()

    page, size = clamp(page, page_size)
    rows = db.execute(
        select(
            LogisticsConsignment.id,
            LogisticsConsignment.mo_no,
            LogisticsConsignment.customer_name,
            LogisticsConsignment.order_type,
            LogisticsConsignment.current_status,
        )
        .where(*conditions)
        .order_by(LogisticsConsignment.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()

    return _set(total, [
        {
            "id": oid,
            "reference": mo or f"LOG-{oid}",
            "detail": customer,
            "meta": _joined(kind or "type not stated", status),
            "badge": kind or "not stated",
        }
        for oid, mo, customer, kind, status in rows
    ], page, size, unit="order")
