from app.dashboard.logistics.calculations import (
    shipments_kpis, cost_per_kg_by_country,
    packing_kpis, packing_cost_kpis,
    transport_kpis, transport_status, TRANSPORT_STATUSES,
    job_customer, job_province,
    count_split,
    dispatch_kpis, dispatch_by_segment, container_type_usage, customer_delays,
)


#=====================================================
# SHIPMENTS
#=====================================================

def serialize_shipments(orders):
    return {
        "kpis": shipments_kpis(orders),
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


def serialize_packing(packages):
    return {
        "kpis": packing_kpis(packages),
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
