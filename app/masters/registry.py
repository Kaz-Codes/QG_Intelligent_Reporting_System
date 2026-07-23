from app.masters.models import (
    Branch, ClearingAgent, Item, Port, Supplier, Works,
)
from app.masters.schemas import (
    BranchCreateSchema, BranchUpdateSchema, ClearingAgentCreateSchema,
    ClearingAgentUpdateSchema, ItemCreateSchema, ItemUpdateSchema,
    PortCreateSchema, PortUpdateSchema, SupplierCreateSchema,
    SupplierUpdateSchema, WorksCreateSchema, WorksUpdateSchema,
)

#-----------------------------------------------------
# THE SIX MASTER LISTS, DESCRIBED ONCE
#
# Every master has the same shape of screen and the same
# handful of operations, so instead of six near identical
# route files there is one description of each master here
# and one set of routes that read from it. The url key is
# the same word the masters screen uses for its tabs, so
# /masters/supplier lines up with the Suppliers tab.
#
# inline    can this master be created in the middle of
#           data entry. Branch and Works cannot.
# has_hs    does this master carry a list of H.S. codes.
#           Only Item does.
#-----------------------------------------------------

MASTERS = {
    "supplier": {
        "model": Supplier,
        "create_schema": SupplierCreateSchema,
        "update_schema": SupplierUpdateSchema,
        "noun": "supplier",
        "inline": True,
        "has_hs": False,
    },
    "branch": {
        "model": Branch,
        "create_schema": BranchCreateSchema,
        "update_schema": BranchUpdateSchema,
        "noun": "branch",
        "inline": False,
        "has_hs": False,
    },
    "works": {
        "model": Works,
        "create_schema": WorksCreateSchema,
        "update_schema": WorksUpdateSchema,
        "noun": "works",
        "inline": False,
        "has_hs": False,
    },
    "port": {
        "model": Port,
        "create_schema": PortCreateSchema,
        "update_schema": PortUpdateSchema,
        "noun": "port",
        "inline": True,
        "has_hs": False,
    },
    "agent": {
        "model": ClearingAgent,
        "create_schema": ClearingAgentCreateSchema,
        "update_schema": ClearingAgentUpdateSchema,
        "noun": "clearing agent",
        "inline": True,
        "has_hs": False,
    },
    "item": {
        "model": Item,
        "create_schema": ItemCreateSchema,
        "update_schema": ItemUpdateSchema,
        "noun": "item",
        "inline": True,
        "has_hs": True,
    },
}

# The order the tabs appear in on the masters screen.
MASTER_ORDER = ["supplier", "branch", "works", "port", "agent", "item"]


#--------------------------------
# LOOK ONE UP, OR SAY IT DOES NOT EXIST
#
# A url with a master key nobody defined is a 404, the same
# as asking for a row that is not there.
#--------------------------------

def get_master_config(master):
    from fastapi import HTTPException

    config = MASTERS.get(master)

    if config is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown master list"
        )

    return config
