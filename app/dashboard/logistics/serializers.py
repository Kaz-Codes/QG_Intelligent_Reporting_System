from app.dashboard.logistics.calculations import (
    shipments_kpis, cost_per_kg_by_country,
    packing_kpis, packing_cost_kpis,
    transport_kpis, transport_status, TRANSPORT_STATUSES,
    job_customer, job_province,
    count_split,
    dispatch_kpis, dispatch_by_segment, container_type_usage, customer_delays,
    DELIVERED, PACKED, TRANSPORT_DELIVERED, TRANSPORT_IN_PROGRESS,
)
from app.dashboard.logistics import references as refs


#=====================================================
# SHIPMENTS
#=====================================================

def serialize_shipments(orders, coverage=None, notes=None):
    return {
        "kpis": shipments_kpis(orders),
        # What the source holds against what the window caught, and where the
        # figures rest on a partly-filled column — same treatment as every
        # other dashboard, so this screen is no longer the quiet one.
        "coverage": coverage,
        "data_notes": notes or [],
        "references": refs.shipment_sets(orders, DELIVERED),
        "status_split": count_split(orders, lambda o: o.current_status),
        "cost_per_kg_by_country": cost_per_kg_by_country(orders),

        # KPI document
        "dispatch_kpis": dispatch_kpis(orders),
        "dispatch_by_segment": dispatch_by_segment(orders),
        "container_type_usage": container_type_usage(orders),
        "customer_delays": customer_delays(orders),
    }


#=====================================================
# PACKING
#=====================================================

def _order_field(package, field):
    order = package.consignment
    return getattr(order, field) if order else None


def serialize_packing(packages, coverage=None, notes=None):
    return {
        "kpis": packing_kpis(packages),
        "coverage": coverage,
        "data_notes": notes or [],
        "references": refs.packing_sets(packages, PACKED),
        # KPI document
        "packing_cost_kpis": packing_cost_kpis(packages),
        "status_split": count_split(packages, lambda p: p.status),
        "by_category": count_split(packages, lambda p: _order_field(p, "department")),
        "by_business_type": count_split(packages, lambda p: _order_field(p, "order_type")),
        "by_customer": count_split(packages, lambda p: _order_field(p, "customer_name"))[:8],
    }


#=====================================================
# TRANSPORT
#=====================================================

def serialize_transport(jobs, links, coverage=None, notes=None):
    return {
        "kpis": transport_kpis(jobs),
        "coverage": coverage,
        "data_notes": notes or [],
        "references": refs.transport_sets(
            jobs, transport_status, TRANSPORT_DELIVERED, TRANSPORT_IN_PROGRESS
        ),
        "status_split": count_split(jobs, transport_status, order=TRANSPORT_STATUSES),
        "by_movement_type": count_split(jobs, lambda j: j.movement_type),
        "by_transporter": count_split(jobs, lambda j: j.transporter_name)[:8],
        "by_payment_status": count_split(jobs, lambda j: j.payment_status),
        "by_customer": count_split(jobs, lambda j: job_customer(j, links))[:8],
        "by_province": count_split(jobs, lambda j: job_province(j, links)),
    }
