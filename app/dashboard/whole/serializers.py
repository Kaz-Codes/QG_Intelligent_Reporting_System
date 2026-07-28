from app.dashboard.imports import calculations as imports_calc
from app.dashboard.logistics import calculations as logistics_calc
from app.dashboard.whole import calculations as whole_calc

#-------------------------------------
# ASSEMBLE THE OVERALL SUMMARY
#
# The headline numbers from both sides, the attention list
# and the health light, plus the two status splits and the
# top suppliers so the summary screen has something to draw
# without opening either module.
#-------------------------------------

def serialize_overall_dashboard(data):
    imports = data["imports"]
    logistics = data["logistics"]

    alert_list = whole_calc.alerts(imports, logistics)

    return {
        "kpis": whole_calc.kpis(imports, logistics),
        "health": whole_calc.health(alert_list),
        "alerts": alert_list,

        "imports_status_split": imports_calc.status_split(imports),
        "logistics_status_split": logistics_calc.status_split(logistics),

        "top_suppliers": imports_calc.value_by_supplier(imports),

        "import_value_trend": imports_calc.monthly_value_trend(imports),
        "logistics_cost_trend": logistics_calc.monthly_cost_trend(logistics)
    }
