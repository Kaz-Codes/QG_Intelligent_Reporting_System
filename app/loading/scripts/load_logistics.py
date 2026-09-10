## LOISTICS LOADERS

from app.loading.scripts.logistics.load_01_logistics import load_logistics
from app.loading.scripts.logistics.load_03_trucking import load_trucking

## LOADING AND POST LOADING FUNCTIONS

from app.loading.scripts.load_all import load_data
from app.loading.scripts.load_all import run_post_load_steps


load_data("Logistics", load_logistics)
load_data("Trucking", load_trucking)

run_post_load_steps()