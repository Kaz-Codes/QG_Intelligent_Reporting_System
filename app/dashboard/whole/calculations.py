from app.dashboard.imports import calculations as imports_calc
from app.dashboard.logistics import calculations as logistics_calc

#-------------------------------------
# THE NUMBERS THE OVERALL SUMMARY SHOWS
#
# The overall dashboard does not compute much of its own. It
# leans on the imports and logistics calculations and puts
# the two sides next to each other, then reads a few
# attention points and a health level off the combined
# picture.
#-------------------------------------


#-------------------------------------
# THE HEADLINE NUMBERS FROM BOTH SIDES
#-------------------------------------

def kpis(imports, logistics):
    import_kpis = imports_calc.kpis(imports)
    logistics_kpis = logistics_calc.kpis(logistics)

    return {
        "total_import_value_pkr": import_kpis["total_value_pkr"],
        "total_logistics_cost": logistics_kpis["total_logistics_cost"],
        "consignments": import_kpis["consignments_shown"],
        "open_imports": import_kpis["open"],
        "under_clearance": import_kpis["under_clearance"],
        "suppliers": import_kpis["suppliers"],
        "logistics_orders": logistics_kpis["orders_shown"],
        "open_logistics_orders": logistics_kpis["open"],
        "delivered_logistics_orders": logistics_kpis["delivered"]
    }


#-------------------------------------
# WHAT NEEDS ATTENTION
#
# A short list of things worth a second look, read straight
# off the data. Each one carries a level so the front end can
# colour it. Only points that actually apply are returned.
#-------------------------------------

def alerts(imports, logistics):
    found = []

    under_clearance = [
        c for c in imports
        if c.current_status == imports_calc.UNDER_CLEARANCE_STATUS
    ]
    if under_clearance:
        found.append({
            "level": "medium",
            "message": str(len(under_clearance)) + " consignment(s) under custom clearance"
        })

    no_rate = [c for c in imports if c.exchange_rate is None]
    if no_rate:
        found.append({
            "level": "low",
            "message": str(len(no_rate)) + " consignment(s) have no exchange rate booked yet"
        })

    open_orders = [
        c for c in logistics
        if c.current_status != logistics_calc.DELIVERED_STATUS
    ]
    if open_orders:
        found.append({
            "level": "low",
            "message": str(len(open_orders)) + " logistics order(s) not delivered yet"
        })

    return found


#-------------------------------------
# ONE WORD FOR HOW THINGS ARE GOING
#
# Green when nothing is flagged, amber when a few things are,
# red when a lot is. A rough read, but enough for a light on
# the top of the screen.
#-------------------------------------

def health(alert_list):
    high = len([a for a in alert_list if a["level"] == "high"])

    if high or len(alert_list) >= 3:
        return {"level": "risk", "message": "Several things need attention"}

    if alert_list:
        return {"level": "watch", "message": "A few things need attention"}

    return {"level": "healthy", "message": "Everything looks in order"}
