## IMPORTS LOADERS
#
# A ONE-OFF MIGRATION SCRIPT, NOT PART OF ANY ROUTINE RELOAD.
#
# load_all.py stopped calling load_05_consignments (and the other four loaders
# here) once the app became the system of record for imports — see its module
# docstring. This file is what remains for loading a brand-new workbook onto
# an EMPTY database, run deliberately, never against one an operator has
# already touched (see CLAUDE.md, "Loading is an explicit CLI, never an
# import side effect").
#
# Without the __main__ guard below, `import
# app.loading.scripts.load_imports` — from a test, a REPL, another script —
# ran every load_data() call as a side effect of the import, dropping and
# reloading data nobody asked to touch.

from app.loading.database_connection import cursor, connection
from app.loading.scripts.imports.load_01_suppliers import load_suppliers
from app.loading.scripts.imports.load_02_branches import load_branches
from app.loading.scripts.imports.load_03_clearing_agent import load_clearing_agent
from app.loading.scripts.imports.load_04_ports import load_ports
from app.loading.scripts.imports.load_05_consignments import load_consignments

## LOADING AND POST LOADING FUNCTIONS

from app.loading.scripts.load_all import load_data
from app.loading.scripts.load_all import run_post_load_steps


def run():
    load_data("Suppliers", load_suppliers)
    load_data("Branches", load_branches)
    load_data("Clearing Agent", load_clearing_agent)
    load_data("Port", load_ports)
    load_data("Consignments", load_consignments)

    run_post_load_steps()


if __name__ == "__main__":
    run()
