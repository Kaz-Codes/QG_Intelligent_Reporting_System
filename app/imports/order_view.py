"""Reading an ORDER's values off one of its batches.

WHY THIS EXISTS RATHER THAN `consignment.batch_group.supplier.name` AT 40 SITES

Supplier, origin, currency, consignment type, incoterm, the payment instrument
and number, the exchange rate and its booking, and the header branch are all
facts about the ORDER, so they live once on `consignment_batch_groups` and a
batch reads them through its group (design sections 3.3 and 3.8). Spelled out at
the call site that is:

    consignment.batch_group.supplier.name if consignment.batch_group
        and consignment.batch_group.supplier else None

three clauses of navigation around one value, repeated wherever a supplier name
is wanted. These accessors say the same thing in one clause and put the
null-handling in one place.

THE SECOND REASON, WHICH IS THE LOAD-BEARING ONE: these are the functions that
absorb the next change. When the mapped attributes come off `Consignment`
entirely, the bridge is here and the call sites do not move again. Writing the
navigation out by hand at every site would mean editing every site twice.

WHAT THIS IS NOT. It is not a compatibility shim that lets old code keep
pretending a consignment owns these values — the call sites say `order_supplier`,
not `.supplier`, so a reader can see the value belongs to the order. That
distinction is the whole point: the navigation is hidden, the OWNERSHIP is not.
"""

from app.enums import PriceBasis



def order_of(consignment):
    """The order a batch belongs to. None only on an unsaved object."""
    return getattr(consignment, "batch_group", None)


def _field(consignment, name):
    order = order_of(consignment)
    return getattr(order, name, None) if order is not None else None


def _related_name(consignment, relation):
    order = order_of(consignment)
    if order is None:
        return None
    related = getattr(order, relation, None)
    return related.name if related is not None else None


#--- the masters the order points at ---

def order_supplier(consignment):
    """The Supplier row, or None."""
    order = order_of(consignment)
    return getattr(order, "supplier", None) if order is not None else None


def order_supplier_name(consignment):
    return _related_name(consignment, "supplier")


def order_supplier_id(consignment):
    """The supplier's id, without loading the Supplier row.

    For counting distinct suppliers, where the name is not wanted and loading
    one master per consignment to read an id would be a query per row.
    """
    return _field(consignment, "supplier_id")


def order_branch(consignment):
    """The order's header-level branch — `works_branch`, which succeeded BOTH
    the free-text `works` column and the old header `branch_id`. Works and
    Branch were always the same thing to the business."""
    order = order_of(consignment)
    return getattr(order, "works_branch", None) if order is not None else None


def order_branch_name(consignment):
    return _related_name(consignment, "works_branch")


def order_branch_id(consignment):
    return _field(consignment, "works_branch_id")


#--- the order's own columns ---

def order_origin(consignment):
    return _field(consignment, "origin")


def order_currency(consignment):
    return _field(consignment, "currency")


def order_type(consignment):
    return _field(consignment, "consignment_type")


def order_incoterm(consignment):
    return _field(consignment, "incoterm")


def order_payment_instrument(consignment):
    return _field(consignment, "payment_instrument")


def order_instrument_number(consignment):
    return _field(consignment, "instrument_number")


def order_exchange_rate(consignment):
    return _field(consignment, "exchange_rate")


def order_rate_booked_on(consignment):
    return _field(consignment, "rate_booked_on")


def order_rate_source(consignment):
    return _field(consignment, "rate_source")


#--- identity ---

#-------------------------------------------------------------------
# THE SAME IDEA ONE LEVEL DOWN: AN ORDER LINE, READ OFF A SHIPMENT LINE
#
# `consignment_items` is what a batch CARRIED; `consignment_order_items` is what
# was BOUGHT. So the item's identity, its price and the requisition details live
# on the order line, and a shipment line reaches them through `order_item`.
#
# Same two reasons as the header accessors above: `line.order_item.item_name if
# line.order_item else None` at forty call sites is noise, and when something
# else moves, it moves here rather than at forty sites.
#
# WHAT STAYS ON THE SHIPMENT LINE, and is therefore NOT here: `quantity` (the
# quantity ALLOCATED to this batch), `eta_works`, `elc`/`alc` and their audit
# columns, the physical weights and dimensions, `batch_no`. Landed cost is
# incurred per arrival; two batches of one item legitimately land at different
# costs.
#-------------------------------------------------------------------

def order_line(line):
    """The order line a shipment line is an allocation against."""
    return getattr(line, "order_item", None)


def _line_field(line, name):
    order_item = order_line(line)
    return getattr(order_item, name, None) if order_item is not None else None


def line_item_name(line):
    return _line_field(line, "item_name")


def line_item_code(line):
    return _line_field(line, "item_code")


def line_item_id(line):
    return _line_field(line, "item_id")


def line_placeholder_name(line):
    return _line_field(line, "placeholder_name")


def line_specification(line):
    return _line_field(line, "specification")


def line_hs_code(line):
    return _line_field(line, "hs_code")


def line_unit_price(line):
    return _line_field(line, "unit_price")


#---------------------------------------------------------------------------
# HOW A LINE IS PRICED - enums.PriceBasis, design revision 14
#
#     quantity basis   quantity x unit_price
#     weight   basis   quantity x unit_weight x weight_unit_price
#
# THE BASIS SELECTS THE RATE; THE PER-BATCH QUANTITY KEEPS DOING THE
# MULTIPLYING. That is the whole design answer and it is why nothing else
# moved: `unit_weight` is kilograms PER UNIT (models.py says so explicitly,
# against `ConsignmentItem.net_weight`, which is the batch's TOTAL), so both
# formulas are `quantity x (something per unit)`. `recompute_derived` stays
# where it is, and two batches of one order still sum to the order's value.
#
# THE WRONG ANSWER, named so nobody proposes it later: valuing on
# `ConsignmentItem.net_weight x weight_unit_price` - the batch's MEASURED total
# weight. It looks more accurate and is not. `net_weight` is entered after
# arrival and is NULL on nearly every line, so a line would value at nothing
# until somebody weighed it and an order's value would drift as weights came
# in; and it double-counts the moment anyone multiplies by quantity again.
#
# ONE FIELD IS AUTHORITATIVE, THE OTHER IS NOT READ. Under the weight basis
# `unit_price` is ignored entirely, and vice versa. The stored value is never a
# blend of the two, which is what keeps a column of unit prices summable.
#---------------------------------------------------------------------------

def line_price_basis(line):
    """Which formula this line is priced by. Defaults to quantity.

    NOT NULL with a server default, so the fallback is defensive rather than
    load-bearing - an in-session object whose attribute has been expired reads
    None, and a valuation is not the place to discover that.
    """
    basis = _line_field(line, "price_basis")
    return basis or PriceBasis.QUANTITY.value


def line_weight_unit_price(line):
    return _line_field(line, "weight_unit_price")


def line_unit_weight(line):
    return _line_field(line, "unit_weight")


def line_effective_unit_price(line):
    """What one unit of this line costs, whichever basis it is priced on.

    THE ONE PYTHON DEFINITION. Every Python valuation multiplies the batch
    line's quantity by this, so a basis change reaches `recompute_derived`, the
    two dashboard figures and the reports column without any of them knowing
    the rule.

    RETURNS None RATHER THAN ZERO when the basis is weight and either input is
    missing. A weight-priced line with no weight is a line nobody has finished
    entering, and every caller already skips a None price - a 0 would quietly
    value it at nothing and make the consignment total look complete.
    """
    if line_price_basis(line) == PriceBasis.WEIGHT.value:
        unit_weight = line_unit_weight(line)
        per_kg = line_weight_unit_price(line)
        if unit_weight is None or per_kg is None:
            return None
        return unit_weight * per_kg

    return line_unit_price(line)


def line_uom(line):
    return _line_field(line, "unit_of_measurement")


def line_requisition_type(line):
    return _line_field(line, "requisition_type")


def line_reference_number(line):
    return _line_field(line, "reference_number")


def line_job_number(line):
    return _line_field(line, "job_number")


def line_mo_number(line):
    return _line_field(line, "mo_number")


def line_description(line):
    return _line_field(line, "description")


def line_item_master(line):
    """The `items` master row behind this line, or None."""
    order_item = order_line(line)
    return getattr(order_item, "item", None) if order_item is not None else None


def line_category(line):
    """The item master's category — what the category charts group by."""
    master = line_item_master(line)
    return getattr(master, "category", None) if master is not None else None


#===========================================================================
# DISPLAY IDENTITY - build-order step 1, design section 3.4
#
# TWO VALUES, NOT ONE, and that is the whole point. The requirements table in
# section 0.4:
#
#     situation    consignment number     payment reference
#     one batch    177                    lc6222
#     two batches  177-1, 177-2           lc6222 on BOTH
#
# `177` and `lc6222` are different facts. The number identifies the SHIPMENT;
# the payment reference identifies the ORDER it was bought under, and every
# batch of one LC shares it. Collapsing them - which `consignment_reference()`
# did - means two batches render as two rows carrying one identical label,
# which reads as a duplicate rather than as a split. Harmless while every
# order holds one batch; wrong the moment step 7 creates a second. That is why
# this is a hard prerequisite of step 7 rather than tidy-up.
#
# WHY VALUE-LEVEL PRIMITIVES WITH ORM WRAPPERS OVER THEM, rather than one
# function taking a Consignment. Of the ten call sites this replaces, SEVEN
# are SQL rows - `whole/references.py` x3, `scanner.py` x3,
# `imports/calculations.py` line_reference - that never build an ORM object.
# An ORM-only function would force each of them to either load objects (an
# N+1 across a reference list) or spell the rule out again. Spelling it out
# again is exactly how there came to be seven copies of a one-line rule.
#
# So the rule lives once, in the `*_from` functions, over plain values. The
# wrappers are three lines each and exist for readability at the ORM sites.
#
# WHERE THIS LIVES, and a deliberate divergence: section 3.4 says helpers.py.
# It is here instead because `order_view` imports NOTHING - the dashboards,
# the scanner and cross_module can all reach it with no risk of a cycle,
# whereas `imports/helpers.py` already has to be imported inside functions by
# `serializers.py` to dodge one. A shared definition that half its callers
# cannot import is not shared.
#===========================================================================


def payment_reference_from(payment_instrument, instrument_number):
    """The ORDER's payment reference: mode + number, concatenated, lower case.

    `LC` + `6222` -> `lc6222`. No separator - section 0.4's `lc-78889` was a
    note about how the list renders it today, not a second format.

    RETURNS EMPTY when there is no instrument number, rather than falling back
    to anything. A consignment with no LC number has no payment reference; that
    is a fact about it, not a gap to paper over. `reference_label_from` below
    is where the fallback lives, once.
    """
    number = (str(instrument_number).strip() if instrument_number is not None else "")
    if not number:
        return ""

    mode = (str(payment_instrument).strip().lower() if payment_instrument else "")
    if not mode:
        return number

    # DO NOT PRINT THE MODE TWICE. If the number already begins with it, the
    # operator has typed the instrument type into the number field - measured:
    # one order holds mode `CAD` and number `CAD`, which concatenates to
    # `cadCAD`. Prepending regardless would also turn a number keyed as
    # "LC6222" into `lclc6222`, and that is the likelier data-entry habit of
    # the two. This does not clean the data; it declines to make it worse.
    if number.lower().startswith(mode):
        return number.lower()

    return f"{mode}{number}"


def consignment_number_from(founding_consignment_id, batches_ever, batch_sequence):
    """The SHIPMENT's number: `177`, or `177-2` once an order has split.

    READS THE FOUNDING BATCH'S ID, NEVER THE ROW'S OWN. On batch 2 those are
    different integers, and the row's own id belongs to no number anyone can
    look up (section 0.4). This is the distinction the whole function exists
    for - a display number derived from `consignment.id` is correct today and
    silently wrong on the first split.

    THE SUFFIX IS STEP 7'S and is deliberately live here already, driven by
    `batches_ever`: an order that has EVER held two batches suffixes both,
    permanently, even if one is later deleted (section 3.5). Today
    `batches_ever` is 1 everywhere, so every number renders bare and nothing
    changes on screen - which is the point. Step 7 sets the column; it does
    not come back here.
    """
    if founding_consignment_id is None:
        return ""

    number = str(founding_consignment_id)
    if (batches_ever or 1) > 1 and batch_sequence is not None:
        return f"{number}-{batch_sequence}"
    return number


def reference_label_from(payment_instrument, instrument_number,
                         founding_consignment_id, batches_ever, batch_sequence):
    """What a list row, a notification or an export cell actually prints.

    The payment reference, falling back to the CONSIGNMENT NUMBER when the
    order carries no instrument number.

    `IMP-{id}` IS GONE - STEP 8. It was the fallback from step 1 until the
    consignment number reached a screen, and the reasoning recorded for its
    removal was that the number would then sit beside the reference and the
    reference could simply go blank. CHECKING THE CALLERS SHOWED THAT PREMISE
    DOES NOT HOLD HERE. Not one of this function's callers is an imports
    screen: they are the dashboard drill-downs, the notification payloads, the
    activity log and the reports `ref` column, and each renders ONE string with
    no second field beside it. The imports list and detail - the two screens
    that DO now show the number - never called this at all; they render
    `payment_reference` directly. Blanking would have removed the only
    identifier those places have.

    What replaces it is the real number rather than a made-up token. `IMP-184`
    resolved to nothing anyone could look up, and on a later batch it was
    additionally wrong: batch 2 of order 177 printed `IMP-184` beside a
    sibling printing `IMP-177`, so one order's two shipments carried two
    unrelated labels, neither of which was the number. `177-1` / `177-2` is
    both correct and lookupable.

    THE SIGNATURE CHANGED ON PURPOSE. It takes the three numbering values
    rather than a consignment id, so a caller that has not been updated raises
    a TypeError rather than quietly passing `consignment.id` - the exact
    substitution section 0.4 bans, and the one a same-arity change would have
    let through unnoticed.
    """
    return payment_reference_from(payment_instrument, instrument_number) \
        or consignment_number_from(founding_consignment_id, batches_ever,
                                   batch_sequence)


#---------------------------------------------------------------------------
# THE ORM WRAPPERS. Same rule, for callers that already hold a Consignment.
#---------------------------------------------------------------------------

def payment_reference(consignment):
    """`payment_reference_from` over a Consignment. Empty when there is none."""
    return payment_reference_from(
        order_payment_instrument(consignment),
        order_instrument_number(consignment),
    )


def consignment_number(consignment):
    """`consignment_number_from` over a Consignment."""
    order = order_of(consignment)
    if order is None:
        return ""

    return consignment_number_from(
        getattr(order, "founding_consignment_id", None),
        getattr(order, "batches_ever", 1),
        getattr(consignment, "batch_sequence", None),
    )


def reference_label(consignment):
    """`reference_label_from` over a Consignment - the number as the fallback."""
    return payment_reference(consignment) or consignment_number(consignment)
