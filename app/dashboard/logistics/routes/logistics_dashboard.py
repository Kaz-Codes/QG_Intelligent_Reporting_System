from app.dashboard.logistics.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.logistics.helpers import (
    fetch_orders, fetch_filtered_orders,
    fetch_packages, fetch_filtered_packages,
    fetch_trucking, fetch_filtered_trucking, logistics_links,
)
from app.dashboard.logistics.serializers import (
    serialize_shipments, serialize_packing, serialize_transport,
)
from app.dashboard.logistics.calculations import (
    shipment_stage, transport_status, SHIPMENT_STAGES, TRANSPORT_STATUSES,
    job_customer, job_province,
)
from app.accounts.permissions import CAN_VIEW_LOGISTICS_DASHBOARD
from typing import Optional

from app.dashboard.period import resolve_period, serialize_period
from app.dashboard.data_quality import coverage_note, collect
from app.dashboard.logistics.helpers import (
    shipments_coverage, packing_coverage, transport_coverage, order_type_counts,
    fetch_undated_orders,
    SHIPMENT_DATE_OPTIONS, SHIPMENT_DATE_DEFAULT,
    PACKING_DATE_OPTIONS, PACKING_DATE_DEFAULT,
    TRANSPORT_DATE_OPTIONS, TRANSPORT_DATE_DEFAULT,
    NOT_STATED, UNCLASSIFIED,
)
from datetime import date


#=====================================================
# SHIPMENTS  — GET /dashboard/logistics/shipments
#=====================================================

@router.get("/shipments")
def shipments_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    stage : Optional[list[str]] = Query(None),
    shipping_line : Optional[list[str]] = Query(None),
    country : Optional[list[str]] = Query(None),
    customer : Optional[list[str]] = Query(None),
    etd_from : Optional[date] = None,
    etd_to : Optional[date] = None,
    search : Optional[str] = None,
    # The dashboard-wide window. Both omitted -> the current month.
    date_from : Optional[date] = None,
    date_to : Optional[date] = None,
    # Which date it applies to: etd (sailing) | eta (arrival).
    date_field : Optional[str] = None,
    ):

    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS_DASHBOARD, db)

        all_orders = fetch_orders(db)
        period_from, period_to, period_kind = resolve_period(date_from, date_to)

        orders = fetch_filtered_orders(
            db, status, shipping_line, country, customer, etd_from, etd_to, search,
            period_from, period_to, date_field,
        )

        cover = shipments_coverage(db, period_from, period_to, date_field)
        stated = sum(1 for o in orders if o.order_type)
        notes = collect(
            coverage_note(
                cover["rows_in_period"], cover["rows_total"], "logistics orders",
                cover["date_field"],
                "Orders with no date in that column fall in no period at all.",
            ),
            coverage_note(
                stated, len(orders), "orders in this period",
                "a local/export type",
                "The Orders tile counts the split over the whole book, because "
                "local orders carry no date and so fall in no period at all.",
            ),
        )

        # Stage is a derived roll-up of the status, so it is filtered here.
        if stage:
            wanted = set(stage)
            orders = [o for o in orders if shipment_stage(o) in wanted]

        statuses = set()
        shipping_lines = set()
        countries = set()
        customers = set()
        for o in all_orders:
            if o.current_status:
                statuses.add(o.current_status)
            if o.shipping_line:
                shipping_lines.add(o.shipping_line)
            if o.origin_country:
                countries.add(o.origin_country)
            if o.customer_name:
                customers.add(o.customer_name)

        data = {
            **serialize_shipments(
                orders, cover, notes,
                # Undated orders sit outside every window, so they cannot come
                # out of the filtered list and are fetched on their own.
                undated=fetch_undated_orders(db, date_field),
            ),
            "period": serialize_period(period_from, period_to, period_kind),
            "date_field": date_field or SHIPMENT_DATE_DEFAULT,
            "date_field_options": SHIPMENT_DATE_OPTIONS,
            # Export against local, counted IN THE WINDOW, with the orders no
            # window can reach reported alongside — see order_type_counts.
            "order_type_counts": order_type_counts(
                db, period_from, period_to, date_field),
            "statuses": sorted(statuses),
            "stages": SHIPMENT_STAGES,
            "shipping_lines": sorted(shipping_lines),
            "countries": sorted(countries),
            "customers": sorted(customers),
        }
        return {"status_code": 200, "detail": "Shipments dashboard fetched", "data": data}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


#=====================================================
# PACKING  — GET /dashboard/logistics/packing
#=====================================================

@router.get("/packing")
def packing_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    works : Optional[list[str]] = Query(None),
    product_category : Optional[list[str]] = Query(None),
    business_type : Optional[list[str]] = Query(None),
    customer : Optional[list[str]] = Query(None),
    packing_from : Optional[date] = None,
    packing_to : Optional[date] = None,
    search : Optional[str] = None,
    date_from : Optional[date] = None,
    date_to : Optional[date] = None,
    # packed | rfd
    date_field : Optional[str] = None,
    ):

    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS_DASHBOARD, db)

        all_packages = fetch_packages(db)
        period_from, period_to, period_kind = resolve_period(date_from, date_to)

        packages = fetch_filtered_packages(
            db, status, works, product_category, business_type, customer,
            packing_from, packing_to, search,
            period_from, period_to, date_field,
        )

        cover = packing_coverage(db, period_from, period_to, date_field)
        costed = sum(1 for p in packages if p.actual_packing_cost)
        notes = collect(
            coverage_note(
                cover["rows_in_period"], cover["rows_total"], "packages",
                cover["date_field"],
            ),
            coverage_note(
                costed, len(packages), "packages in this period",
                "an actual packing cost",
                "Packing savings cannot be computed without it, so it is "
                "reported as unavailable rather than as zero.",
            ),
        )

        statuses = set()
        works_list = set()
        categories = set()
        business_types = set()
        customers = set()
        for p in all_packages:
            if p.status:
                statuses.add(p.status)
            if p.packing_works:
                works_list.add(p.packing_works)
            order = p.consignment
            if order:
                if order.department:
                    categories.add(order.department)
                if order.order_type:
                    business_types.add(order.order_type)
                if order.customer_name:
                    customers.add(order.customer_name)

        data = {
            **serialize_packing(packages, cover, notes),
            "period": serialize_period(period_from, period_to, period_kind),
            "date_field": date_field or PACKING_DATE_DEFAULT,
            "date_field_options": PACKING_DATE_OPTIONS,
            "statuses": sorted(statuses),
            "works": sorted(works_list),
            "product_categories": sorted(categories),
            "business_types": sorted(business_types),
            "customers": sorted(customers),
        }
        return {"status_code": 200, "detail": "Packing dashboard fetched", "data": data}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


#=====================================================
# TRANSPORT  — GET /dashboard/logistics/transport
#=====================================================

@router.get("/transport")
def transport_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    movement_type : Optional[list[str]] = Query(None),
    source : Optional[list[str]] = Query(None),
    payment_status : Optional[list[str]] = Query(None),
    transporter : Optional[list[str]] = Query(None),
    customer : Optional[list[str]] = Query(None),
    province : Optional[list[str]] = Query(None),
    exec_from : Optional[date] = None,
    exec_to : Optional[date] = None,
    search : Optional[str] = None,
    date_from : Optional[date] = None,
    date_to : Optional[date] = None,
    # etd (execution) | eta (arrival at works)
    date_field : Optional[str] = None,
    ):

    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS_DASHBOARD, db)

        all_jobs = fetch_trucking(db)
        period_from, period_to, period_kind = resolve_period(date_from, date_to)

        jobs = fetch_filtered_trucking(
            db, movement_type, source, payment_status, transporter,
            exec_from, exec_to, search,
            period_from, period_to, date_field,
        )

        cover = transport_coverage(db, period_from, period_to, date_field)
        typed = sum(1 for j in jobs if j.movement_type)
        freighted = sum(1 for j in jobs if j.actual_freight is not None)
        notes = collect(
            coverage_note(
                cover["rows_in_period"], cover["rows_total"], "trucking jobs",
                cover["date_field"],
            ),
            coverage_note(
                typed, len(jobs), "jobs in this period", "a movement type",
                "Those sit in the Unclassified bucket rather than being folded "
                "into Inbound or Outbound, which cannot be inferred.",
            ),
            coverage_note(
                freighted, len(jobs), "jobs in this period", "a freight figure",
                "Cost totals cover only the jobs that recorded one.",
            ),
        )

        # customer / city / province are resolved from the linked logistics
        # order (a local logistics consignment moved to trucking carries them).
        links = logistics_links(db, all_jobs)

        # Transport status is a roll-up over the vehicles, so it is filtered here.
        if status:
            wanted = set(status)
            jobs = [j for j in jobs if transport_status(j) in wanted]
        if customer:
            wanted = set(customer)
            jobs = [j for j in jobs if job_customer(j, links) in wanted]
        if province:
            wanted = set(province)
            jobs = [j for j in jobs if job_province(j, links) in wanted]

        movement_types = set()
        sources = set()
        payment_statuses = set()
        transporters = set()
        customers = set()
        provinces = set()
        for j in all_jobs:
            if j.movement_type:
                movement_types.add(j.movement_type)
            if j.source:
                sources.add(j.source)
            if j.payment_status:
                payment_statuses.add(j.payment_status)
            if j.transporter_name:
                transporters.add(j.transporter_name)
            c = job_customer(j, links)
            if c:
                customers.add(c)
            p = job_province(j, links)
            if p:
                provinces.add(p)

        data = {
            **serialize_transport(jobs, links, cover, notes),
            "period": serialize_period(period_from, period_to, period_kind),
            "date_field": date_field or TRANSPORT_DATE_DEFAULT,
            "date_field_options": TRANSPORT_DATE_OPTIONS,
            # Offered as a selectable bucket: 207 jobs genuinely say nothing,
            # and there is no way to tell which way they went.

            "statuses": TRANSPORT_STATUSES,
            # The values present, PLUS the bucket for the 207 jobs that state
            # no movement type — a real answer, and selectable as one.
            "movement_types": sorted(movement_types) + [UNCLASSIFIED],
            "sources": sorted(sources),
            "payment_statuses": sorted(payment_statuses),
            "transporters": sorted(transporters),
            "customers": sorted(customers),
            "provinces": sorted(provinces),
        }
        return {"status_code": 200, "detail": "Transport dashboard fetched", "data": data}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()
