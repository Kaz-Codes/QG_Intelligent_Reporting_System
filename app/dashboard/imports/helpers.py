from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload, selectinload

from app.imports.models import (
    Consignment, ConsignmentBatchGroup, ConsignmentItem, ConsignmentOrderItem,
)
from app.imports.demand_dates import EARLIEST_REQUIRED_DATE, earliest_required_date
from app.masters.models import Supplier, Item, Branch
from app.enums import Status
from app.dashboard.period import coverage
from app.reports.helpers import SHAFT_ITEMS


#-------------------------------------
# FETCH THE CONSIGNMENTS THE IMPORTS
# DASHBOARD IS BUILT FROM
#
# Only live consignments count, a deleted one is not part of
# the picture. Items are loaded up front because the value of
# a consignment is worked out from its item lines, and the
# supplier and branch are loaded so they can be grouped by
# name without a query per row.
#-------------------------------------

def fetch_consignments(db):
    # The item MASTER is loaded behind each line as well — the route builds its
    # item_categories dropdown from item.item.category, which lazy-loaded one
    # query per line without this.
    query = select(Consignment).where(
        Consignment.is_deleted == False
    ).options(
        selectinload(Consignment.items).joinedload(ConsignmentItem.item),
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.supplier),
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.works_branch),
    )

    return db.execute(query).scalars().all()


# The two dates a consignment can be reported on, exactly as the Overview
# offers them — "value that ARRIVED in August" and "value that was NEEDED in
# August" are both real questions and they are not the same set. Looked up
# through a map rather than interpolated, so an unknown name cannot reach SQL.
DATE_FIELDS = {
    "eta_works": Consignment.eta_works,
    # THE EARLIEST REQUIRED DATE ACROSS THIS BATCH'S LINES, not a header column.
    # `required_date` is a fact about the demand and lives on the order item now,
    # so a batch carrying three lines has three of them and a column showing one
    # has to aggregate. Imported rather than spelled out here — eleven sites read
    # this and four of them decide window MEMBERSHIP, so a second spelling would
    # change which records a period contains rather than merely restating a
    # number. See app/imports/demand_dates.py.
    "required_date": EARLIEST_REQUIRED_DATE,
}
DATE_FIELD_DEFAULT = "eta_works"

DATE_FIELD_OPTIONS = [
    {"value": "eta_works", "label": "ETA Works"},
    {"value": "required_date", "label": "Required date"},
]


def date_column(field):
    return DATE_FIELDS.get(field or DATE_FIELD_DEFAULT, DATE_FIELDS[DATE_FIELD_DEFAULT])


def source_coverage(db, date_from, date_to, date_field=None):
    """What the consignments table holds, against what the window catches.

    Windowed on the CALLER'S chosen date, so the "latest data is ..." message
    and the jump it offers describe the column actually being filtered on. It
    used to be hardcoded to ETA Works, which sent the user to the wrong month
    the moment they switched to required date.

    Arrived consignments are counted here, because the screen shows them — the
    denominator has to be the population on screen or the coverage percentage
    describes a different table.
    """
    column = date_column(date_field)
    label = "ETA Works" if (date_field or DATE_FIELD_DEFAULT) == "eta_works" else "required date"

    earliest, latest, total = db.execute(
        select(func.min(column), func.max(column), func.count(Consignment.id))
        .where(Consignment.is_deleted == False)
    ).one()

    in_period = db.execute(
        select(func.count(Consignment.id))
        .where(Consignment.is_deleted == False)
        .where(column.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, label)


#-----------------------------------------------------
# LINE-LEVEL FIGURES
#
# Some figures are about LINES, not consignments — shaft value is the clearest:
# a consignment usually carries other items too, so its total says nothing about
# what the shafts inside it were worth.
#
# Those figures must also be DATED BY THE LINE. A consignment groups every sheet
# row sharing a payment reference, and those rows do not all arrive together:
# 19 of 175 consignments carry lines with different ETAs, and 45 individual
# lines have an ETA that is not their header's. Payment ref 65704 is the worked
# example — seven shaft lines worth Rs 10.64m, of which only Rs 8.98m arrived in
# August; the other Rs 1.25m landed on 27 July and was being counted as August
# money because the header said 6 August.
#
# EFFECTIVE LINE DATE = the line's own ETA, or its consignment's where the line
# has none (10 of 450 lines). That fallback is what keeps the line-dated figures
# from quietly dropping rows the sheet did not date.
#-----------------------------------------------------

LINE_ETA = func.coalesce(ConsignmentItem.eta_works, Consignment.eta_works)

# The line's value in PKR, at the consignment's own booked rate — never a live
# one (imports rule 4). There is no stored per-line total to prefer here: the
# sheet's per-line PKR is summed into the consignment's `pkr_total` and not kept
# per row, so this is the only per-line figure available.
LINE_VALUE_PKR = (
    ConsignmentItem.quantity * ConsignmentItem.unit_price * ConsignmentBatchGroup.exchange_rate
)


def line_date_column(date_field):
    """Which date a LINE is filtered on.

    BOTH CHOICES ARE NOW GENUINELY PER LINE, and that is a change in precision
    rather than a repoint. This used to fall back to `Consignment.required_date`
    with a comment saying no line equivalent existed — one does now
    (`consignment_order_items.required_date`), because the requirements moved the
    demand dates onto the item.

    A CONSEQUENCE TO EXPECT, not a bug: under `date_field='required_date'` window
    membership gets stricter. It used to mean "this consignment's header date is
    in the window", which pulled in every line of a qualifying consignment
    including ones needed months outside it. It now means "THIS line was needed
    in the window". Row counts on that filter will fall, and the rows that
    remain are the right ones — the same precision gain CLAUDE.md records for the
    shaft and category filters when reports moved to one row per line.

    Callers must join `ConsignmentOrderItem`; `_line_query` and
    `fetch_shaft_lines` below do.
    """
    if (date_field or DATE_FIELD_DEFAULT) == "required_date":
        return ConsignmentOrderItem.required_date
    return LINE_ETA


def _line_query(shafts_only=False):
    return (
        select(
            ConsignmentItem.id,
            Consignment.id.label("consignment_id"),
            ConsignmentBatchGroup.instrument_number,
            ConsignmentItem.item_name,
            ConsignmentItem.quantity,
            ConsignmentItem.unit_of_measurement,
            ConsignmentItem.unit_price,
            ConsignmentBatchGroup.exchange_rate,
            LINE_ETA.label("line_eta"),
            Consignment.current_status,
            Supplier.name.label("supplier"),
            Branch.name.label("branch"),
            LINE_VALUE_PKR.label("value"),
        )
        .select_from(ConsignmentItem)
        .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
        # The ORDER above the batch, and the ORDER LINE above the shipment line.
        # Supplier and branch are terms of the order and live on the group now;
        # the demand dates live on the order item. Inner joins on both: every
        # consignment has a group and every line has an order item, both NOT
        # NULL since revision A, so there is no row to lose.
        .join(ConsignmentBatchGroup,
              ConsignmentBatchGroup.id == Consignment.batch_group_id)
        .join(ConsignmentOrderItem,
              ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
        .outerjoin(Supplier, Supplier.id == ConsignmentBatchGroup.supplier_id)
        .outerjoin(Branch, Branch.id == ConsignmentBatchGroup.works_branch_id)
        .where(ConsignmentItem.is_deleted.is_(False))
        .where(Consignment.is_deleted.is_(False))
    )


def fetch_period_lines(db, date_from=None, date_to=None, date_field=None,
                       work=None, supplier=None, country=None, shafts_only=False):
    """Every import LINE arriving in the window.

    The basis for this screen's MONEY. Value has to be summed over lines and
    dated by them, or a consignment straddling two months credits all of itself
    to whichever one its header names — ref 65704 reported Rs 10.64m in August
    when Rs 1.25m of it had arrived in July.
    """
    query = _line_query()

    if shafts_only:
        query = query.where(or_(*[ConsignmentItem.item_name.ilike(f"%{name}%")
                                  for name in SHAFT_ITEMS]))
    if date_from is not None and date_to is not None:
        query = query.where(line_date_column(date_field).between(date_from, date_to))
    if work:
        query = query.where(Branch.name == work)
    if supplier:
        query = query.where(Supplier.name == supplier)
    if country:
        query = query.where(ConsignmentBatchGroup.origin == country)

    return db.execute(query.order_by(LINE_VALUE_PKR.desc(), ConsignmentItem.id)).all()


def fetch_shaft_lines(db, date_from=None, date_to=None, date_field=None,
                      work=None, supplier=None, country=None):
    """The shaft item LINES in the window, each with its own date and value.

    Selected from the LINES rather than filtered out of an already
    header-dated consignment list — otherwise a consignment whose header sits
    outside the window would take its in-window lines with it.
    """
    # BUILT ON _line_query, not copied from it. This used to restate the whole
    # select list and all four joins, which is two places for the same query to
    # drift — and the joins just changed (supplier and branch moved to the order,
    # the demand dates to the order line), so the copy would have had to change
    # identically or this tab would have quietly kept reading the old columns.
    query = _line_query().where(
        or_(*[ConsignmentItem.item_name.ilike(f"%{name}%") for name in SHAFT_ITEMS])
    )

    if date_from is not None and date_to is not None:
        query = query.where(line_date_column(date_field).between(date_from, date_to))
    if work:
        query = query.where(Branch.name == work)
    if supplier:
        query = query.where(Supplier.name == supplier)
    if country:
        query = query.where(ConsignmentBatchGroup.origin == country)

    return db.execute(query.order_by(LINE_VALUE_PKR.desc(), ConsignmentItem.id)).all()


def fetch_filtered_consigments(
        db,
        work, status, item_category,
        supplier, country, from_date,
        to_date, mode_of_shipment,
        date_from=None, date_to=None,
        date_field=None, search=None, shafts_only=False,
        include_arrived=True,
    ):

    # Same eager loading as fetch_consignments, plus the item MASTER behind each
    # line (category_delays reads item.item.category). Without these the value,
    # supplier and category figures lazy-load per row — an N+1 across the whole
    # filtered set, which was roughly half the response time before.
    # distinct() because the item_category / work / supplier filters join, and a
    # consignment with several matching lines would otherwise be counted once
    # per line in every figure on the screen.
    query = select(Consignment).where(
        Consignment.is_deleted == False
    ).options(
        # THE ORDER LINE BEHIND EACH SHIPMENT LINE IS NOT OPTIONAL HERE.
        #
        # delivery_delay and category_delays both call
        # demand_dates.earliest_required_date, which walks
        # line.order_item.required_date for every line of every consignment in
        # the filtered set. Without this joinedload that is one query PER LINE
        # across the whole set — the same N+1 the item-master load below was
        # added to kill, and worse, because there are ~2.5 lines per row.
        selectinload(Consignment.items).joinedload(ConsignmentItem.item),
        selectinload(Consignment.items).joinedload(ConsignmentItem.order_item),
        # Supplier and branch hang off the ORDER now, so the group has to come
        # with them or every `.supplier.name` read is a query of its own.
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.supplier),
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.works_branch),
    )

    # ARRIVED AT WORKS IS NO LONGER EXCLUDED BY DEFAULT.
    #
    # It used to be, because this is an operational screen. But the Overview
    # counts every consignment, so the same window reported Rs 262m there and
    # Rs 210m here — a Rs 52.7m gap that was four arrived consignments and
    # nothing else. Two screens quietly answering different questions under the
    # same label is worse than one screen showing finished work.
    #
    # So the FULL set is fetched, and the figures that are genuinely operational
    # (delay, the stage pipeline) split it in Python — each one stating which
    # population it used. `include_arrived=False` is still available for a
    # caller that wants the operational set alone.
    if not include_arrived:
        query = query.where(Consignment.current_status != Status.ARRIVED_AT_WORKS.value)

    if shafts_only:
        # Shafts are matched on the LINE's item name: these names are not in the
        # item master at all, and the line keeps its own copy anyway (rule 12).
        # Same SHAFT_ITEMS list the Overview and Reports use.
        query = query.where(Consignment.id.in_(
            select(ConsignmentItem.consignment_id)
            .where(ConsignmentItem.is_deleted.is_(False))
            .where(or_(*[ConsignmentItem.item_name.ilike(f"%{name}%")
                         for name in SHAFT_ITEMS]))
            .distinct()
            .scalar_subquery()
        ))

    if search:
        # The things somebody actually types to find a consignment: its payment
        # reference, its GD number, the supplier, or an item on it.
        term = f"%{search.strip()}%"
        query = query.where(or_(
            Consignment.gd_number.ilike(term),
            # The payment reference and the origin are terms of the ORDER now.
            Consignment.batch_group.has(or_(
                ConsignmentBatchGroup.instrument_number.ilike(term),
                ConsignmentBatchGroup.origin.ilike(term),
            )),
            Consignment.id.in_(
                select(ConsignmentItem.consignment_id)
                .where(ConsignmentItem.is_deleted.is_(False))
                .where(or_(ConsignmentItem.item_name.ilike(term),
                           ConsignmentItem.item_code.ilike(term)))
                .distinct()
                .scalar_subquery()
            ),
            # Supplier, works/branch and origin are all terms of the ORDER now,
            # so each of these three filters resolves through the group. Matched
            # with `.has(...)` rather than a join so adding a filter cannot
            # change the row count of the others.
            Consignment.batch_group.has(
                ConsignmentBatchGroup.supplier.has(Supplier.name.ilike(term))
            ),
        ))

    if work:
        query = query.where(Consignment.batch_group.has(
            ConsignmentBatchGroup.works_branch.has(Branch.name == work)
        ))

    if status:
       query = query.where(
            Consignment.current_status == status
        )

    if item_category:
        query = (
            query.join(Consignment.items)
                 .join(ConsignmentItem.item)
                 .where(Item.category == item_category)
        )

    if supplier:
        query = query.where(Consignment.batch_group.has(
            ConsignmentBatchGroup.supplier.has(Supplier.name == supplier)
        ))

    if country:
        query = query.where(Consignment.batch_group.has(
            ConsignmentBatchGroup.origin == country
        ))
        
    if from_date:
        query = query.where(Consignment.eta_works >= from_date)
    if to_date:
        query = query.where(Consignment.eta_works <= to_date)

    if mode_of_shipment:
        query = query.where(
            Consignment.mode_of_shipment == mode_of_shipment
        )

    # The dashboard-wide reporting window, on the CALLER'S chosen date — the
    # same choice the Overview's imports section offers, so the two screens can
    # be put on the same window and compared. from_date/to_date above stay as
    # the screen's own explicit ETA range filter.
    #
    # MEMBERSHIP IS BY LINE, not by header. A consignment belongs to the window
    # if ANY of its lines arrives in it, because the rows sharing a payment
    # reference do not all arrive together — 19 of 175 consignments carry lines
    # with different ETAs. Filtering on the header alone both dropped
    # consignments whose header sat outside a window they genuinely delivered
    # into, and pulled in every out-of-window line of the ones it kept.
    if date_from is not None and date_to is not None:
        query = query.where(Consignment.id.in_(
            select(ConsignmentItem.consignment_id)
            .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
            # Needed for the required_date choice, which now reads the ORDER
            # LINE (line_date_column above) rather than falling back to a header
            # column. Joined unconditionally rather than only for that branch:
            # order_item_id is NOT NULL so it loses no row, and a join that
            # appears and disappears with a parameter is how the two branches
            # come to disagree about which rows they see.
            .join(ConsignmentOrderItem,
                  ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
            .where(ConsignmentItem.is_deleted.is_(False))
            .where(line_date_column(date_field).between(date_from, date_to))
            .distinct()
            .scalar_subquery()
        ))

    return db.execute(query).unique().scalars().all()





