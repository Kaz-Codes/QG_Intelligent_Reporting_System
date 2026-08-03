from app.dashboard.logistics.calculations import (
    shipments_kpis, cost_per_kg_by_country,
    packing_kpis,
    transport_kpis, transport_status, TRANSPORT_STATUSES,
    job_customer, job_province,
    count_split,
)


#=====================================================
# SHIPMENTS
#=====================================================

def serialize_shipments(orders):
    return {
        "kpis": shipments_kpis(orders),
        "status_split": count_split(orders, lambda o: o.current_status),
        "cost_per_kg_by_country": cost_per_kg_by_country(orders),
    }


#=====================================================
# PACKING
#=====================================================

def _order_field(package, field):
    order = package.consignment
    return getattr(order, field) if order else None


def serialize_packing(packages):
    return {
        "kpis": packing_kpis(packages),
        "status_split": count_split(packages, lambda p: p.status),
        "by_category": count_split(packages, lambda p: _order_field(p, "department")),
        "by_business_type": count_split(packages, lambda p: _order_field(p, "order_type")),
        "by_customer": count_split(packages, lambda p: _order_field(p, "customer_name"))[:8],
    }


#=====================================================
# TRANSPORT
#=====================================================

def serialize_transport(jobs, links):
    return {
        "kpis": transport_kpis(jobs),
        "status_split": count_split(jobs, transport_status, order=TRANSPORT_STATUSES),
        "by_movement_type": count_split(jobs, lambda j: j.movement_type),
        "by_transporter": count_split(jobs, lambda j: j.transporter_name)[:8],
        "by_payment_status": count_split(jobs, lambda j: j.payment_status),
        "by_customer": count_split(jobs, lambda j: job_customer(j, links))[:8],
        "by_province": count_split(jobs, lambda j: job_province(j, links)),
    }
