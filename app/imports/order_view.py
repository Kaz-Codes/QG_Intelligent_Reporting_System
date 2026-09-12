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


def order_reference(consignment):
    """How a consignment is NAMED in a message, a report or a list.

    The payment instrument number, falling back to IMP-{id} for a record that
    has not been given one. One definition, because a notification naming a
    consignment differently from the screen the reader then opens is a
    notification they cannot act on.

    A NOTE ON WHAT THIS CANNOT YET DO. The instrument number is a fact about the
    ORDER, so every batch of one LC returns the SAME reference here — two
    batches render as two rows carrying one label, which reads as a duplicate
    rather than as a split. Fixing that is `consignment_number()` /
    `payment_reference()` (design section 3.4, build-order step 1), which is a
    hard prerequisite of step 7: it is harmless while every order holds one
    batch and wrong the moment one holds two.
    """
    return order_instrument_number(consignment) or f"IMP-{consignment.id}"
