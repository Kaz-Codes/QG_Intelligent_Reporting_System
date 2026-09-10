## IMPORTS LOADERS 

from app.loading.database_connection import cursor, connection
from app.loading.scripts.imports.load_01_suppliers import load_suppliers
from app.loading.scripts.imports.load_02_branches import load_branches
from app.loading.scripts.imports.load_03_clearing_agent import load_clearing_agent
from app.loading.scripts.imports.load_04_ports import load_ports
from app.loading.scripts.imports.load_05_consignments import load_consignments

## LOADING AND POST LOADING FUNCTIONS

from app.loading.scripts.load_all import load_data
from app.loading.scripts.load_all import run_post_load_steps


load_data("Suppliers", load_suppliers)
load_data("Branches", load_branches)
load_data("Clearing Agent", load_clearing_agent)
load_data("Port", load_ports)
load_data("Consignments", load_consignments)

run_post_load_steps()




