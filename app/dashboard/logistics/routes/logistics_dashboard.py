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
    ):

    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS_DASHBOARD, db)

        all_orders = fetch_orders(db)
        orders = fetch_filtered_orders(
            db, status, shipping_line, country, customer, etd_from, etd_to, search
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
            **serialize_shipments(orders),
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
    ):

    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS_DASHBOARD, db)

        all_packages = fetch_packages(db)
        packages = fetch_filtered_packages(
            db, status, works, product_category, business_type, customer,
            packing_from, packing_to, search,
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
            **serialize_packing(packages),
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
    ):

    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS_DASHBOARD, db)

        all_jobs = fetch_trucking(db)
        jobs = fetch_filtered_trucking(
            db, movement_type, source, payment_status, transporter,
            exec_from, exec_to, search,
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
            **serialize_transport(jobs, links),
            "statuses": TRANSPORT_STATUSES,
            "movement_types": sorted(movement_types),
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
