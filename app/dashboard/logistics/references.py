"""
The records behind every logistics KPI.

Same contract as everywhere else (see app/dashboard/references): the list is
COMPLETE, one page travels per request, and where a record has lines under it
the rows ARE the lines — `unit` and `groups` keep the count honest against the
tile it opened from.

THE THREE TABS COUNT THREE DIFFERENT THINGS, and each list says which:

    shipments  ORDERS      — one logistics order per row
    packing    PACKAGES    — one packed package per row, grouped by its order
    transport  JOBS        — one trucking job per row

A packing list therefore reports "678 packages across 745 orders" rather than a
bare number that would look like it disagreed with the Orders tile.
"""

from app.dashboard.references import paginate


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
    return " · ".join(str(p) for p in parts if p) or None


#=====================================================
# SHIPMENTS — one row per ORDER
#=====================================================

def order_reference(order, badge=None):
    return {
        "id": order.id,
        # The number somebody looks an order up by.
        "reference": order.mo_no or order.batch_no or f"LOG-{order.id}",
        "detail": order.customer_name,
        "meta": _joined(
            order.order_type or "type not stated",
            order.origin_country,
            order.current_status,
        ),
        "badge": badge(order) if badge else order.current_status,
    }


def order_references(orders, page=None, page_size=None, badge=None):
    return paginate(
        [order_reference(o, badge) for o in orders], page, page_size,
        unit="order",
    )


#=====================================================
# PACKING — one row per PACKAGE, grouped by its order
#=====================================================

def package_reference(package, badge=None):
    order = package.consignment
    weight = package.gross_weight

    return {
        "id": package.id,
        "reference": (order.mo_no if order else None) or f"PKG-{package.id}",
        "detail": package.colour_code or package.packing_works,
        "meta": _joined(
            order.customer_name if order else None,
            f"{float(weight):,.0f} kg" if weight else None,
            package.status,
        ),
        "badge": badge(package) if badge else package.status,
    }


def package_references(packages, page=None, page_size=None, badge=None):
    """Packages, with the ORDER count alongside so the two tiles reconcile."""
    return paginate(
        [package_reference(p, badge) for p in packages], page, page_size,
        unit="package",
        groups=len({p.consignment_id for p in packages if p.consignment_id}),
        group_unit="order",
    )


#=====================================================
# TRANSPORT — one row per JOB
#=====================================================

def job_reference(job, badge=None):
    return {
        "id": job.id,
        "reference": job.reference_no or f"TRK-{job.id}",
        "detail": job.item_details,
        "meta": _joined(
            job.movement_type or "Unclassified",
            job.transporter_name,
            _joined(job.pickup, job.destination) if (job.pickup or job.destination) else None,
        ),
        "badge": badge(job) if badge else _money(job.actual_freight),
    }


def job_references(jobs, page=None, page_size=None, badge=None):
    return paginate(
        [job_reference(j, badge) for j in jobs], page, page_size, unit="job",
    )


#=====================================================
# THE SETS EACH TILE OPENS
#
# Built here rather than in the serializer so the dashboard payload and the
# /references endpoint cannot drift into selecting different rows for the same
# tile — the bug that had the Shafts tab showing 1 consignment over a list of 7.
#=====================================================

def shipment_sets(orders, delivered_status, page=None, page_size=None,
                  undated=None):
    """The lists each shipments tile opens.

    `undated` is the orders carrying no date in the chosen column — they are in
    no window, so they cannot come out of `orders` and are passed in separately.
    Their tile is the one that would otherwise read a silent zero.
    """
    delivered = [o for o in orders if o.current_status == delivered_status]
    by_type = lambda t: [o for o in orders
                         if (o.order_type == t if t else not o.order_type)]

    sets = {
        "orders": order_references(orders, page, page_size),
        "delivered": order_references(delivered, page, page_size),
        "export": order_references(by_type("Export"), page, page_size),
        "local": order_references(by_type("Local"), page, page_size),
        "not_stated": order_references(by_type(None), page, page_size),
    }
    if undated is not None:
        sets["undated"] = order_references(undated, page, page_size)
    return sets


def packing_sets(packages, packed_status, page=None, page_size=None):
    packed = [p for p in packages if p.status == packed_status]

    return {
        "packages": package_references(packages, page, page_size),
        "packed": package_references(packed, page, page_size),
    }


def transport_sets(jobs, status_of, delivered, in_progress,
                   page=None, page_size=None):
    return {
        "jobs": job_references(jobs, page, page_size),
        "delivered": job_references(
            [j for j in jobs if status_of(j) == delivered], page, page_size),
        "in_progress": job_references(
            [j for j in jobs if status_of(j) == in_progress], page, page_size),
    }
