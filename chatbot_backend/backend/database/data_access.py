"""
Backend interface layer.

This is the ONLY module the frontend pages are allowed to import for data.
Pages never touch the database, the stubs, or any calculation directly —
they call functions here.

Right now every function forwards to stubs/fake_data.py. When the real
backend is ready, we change ONLY the bodies of these functions to call
the real database/analytics modules. The function names and their return
shapes stay identical, so no page code changes.

    Page  ->  backend.data_access  ->  (today) stubs
                                        (later) real database / analytics
"""

from stubs import fake_data as _src

import pandas as pd
from sqlalchemy import text
from backend.db_connection import get_engine


# --- Dashboard -------------------------------------------------------
def dashboard_kpis():
    return _src.get_dashboard_kpis()


def purchase_trend():
    return _src.get_purchase_trend()


def alerts():
    return _src.get_alerts()


# --- Purchases -------------------------------------------------------
def purchases(status="All", supplier="All"):
    return _src.get_purchases(status=status, supplier=supplier)


def supplier_list():
    return _src.get_supplier_list()


# --- Inventory -------------------------------------------------------
def stock(status="All"):
    """Real data: current stock joined to item names, with a computed status.

    The stock table has no item name (it's in `items`) and no stored status,
    so we join for the name and derive `stock_status` here. This keeps the
    return shape identical to what the Inventory page expects, so the page
    does not change.

    NOTE: 'Below reorder' is currently a placeholder rule (available_qty = 0)
    because the stock table has no reorder-level column yet. Replace with a
    real reorder threshold once the business provides one.
    """
    query = text("""
        SELECT
            s.item_code,
            COALESCE(i.item, s.item_code) AS item,
            s.branch,
            s.stock_qty,
            s.available_qty,
            CASE WHEN s.available_qty <= 0 THEN 'Below reorder'
                 ELSE 'OK' END AS stock_status
        FROM public.stock s
        LEFT JOIN public.items i ON i.item_code = s.item_code
        ORDER BY s.item_code
    """)
    df = pd.read_sql(query, get_engine())

    if status != "All":
        df = df[df["stock_status"] == status].reset_index(drop=True)
    return df


# --- Imports ---------------------------------------------------------
def imports(status="All"):
    return _src.get_imports(status=status)


# --- Logistics -------------------------------------------------------
def logistics(kind="Export"):
    return _src.get_logistics(kind=kind)


# --- Assistant -------------------------------------------------------
def ask_assistant(question):
    return _src.ask_assistant(question)


# --- Executive / enriched (added for enterprise dashboard) -----------
def dashboard_kpis_rich():
    return _src.get_dashboard_kpis_rich()


def health():
    return _src.get_health()


def supplier_performance():
    return _src.get_supplier_performance()


def status_split(kind="purchases"):
    return _src.get_status_split(kind=kind)


def aging():
    return _src.get_aging()
