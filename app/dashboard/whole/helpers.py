from app.dashboard.imports.helpers import fetch_consignments as fetch_imports
from app.dashboard.logistics.helpers import fetch_consignments as fetch_logistics


#-------------------------------------
# FETCH EVERYTHING THE OVERALL
# SUMMARY IS BUILT FROM
#
# The overall dashboard sits on top of the imports and the
# logistics data, so it just reuses the fetchers those two
# dashboards already have rather than writing the queries a
# second time.
#-------------------------------------

def fetch_all(db):
    return {
        "imports": fetch_imports(db),
        "logistics": fetch_logistics(db)
    }
