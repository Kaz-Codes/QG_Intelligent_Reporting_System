## LOGISTICS LOADERS
#
# Same status as load_imports.py: a one-off migration script for a brand-new
# workbook onto an empty database, not part of the routine reload, and not
# safe to run as an import side effect. See that file's comment.

from app.loading.scripts.logistics.load_01_logistics import load_logistics
from app.loading.scripts.logistics.load_03_trucking import load_trucking

## LOADING AND POST LOADING FUNCTIONS

from app.loading.scripts.load_all import load_data
from app.loading.scripts.load_all import run_post_load_steps


def run():
    load_data("Logistics", load_logistics)
    load_data("Trucking", load_trucking)

    run_post_load_steps()


if __name__ == "__main__":
    run()