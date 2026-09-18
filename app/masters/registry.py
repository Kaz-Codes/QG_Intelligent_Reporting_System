from app.masters.models import (
    Branch, ClearingAgent, Customer, Item, Port, Supplier, Transporter,
)
from app.masters.schemas import (
    BranchCreateSchema, BranchUpdateSchema, ClearingAgentCreateSchema,
    ClearingAgentUpdateSchema, CustomerCreateSchema, CustomerUpdateSchema,
    ItemCreateSchema, ItemUpdateSchema, PortCreateSchema, PortUpdateSchema,
    SupplierCreateSchema, SupplierUpdateSchema, TransporterCreateSchema,
    TransporterUpdateSchema,
)

#-----------------------------------------------------
# THE MASTER LISTS, DESCRIBED ONCE
#
# Every master has the same shape of screen and the same
# handful of operations, so instead of one near identical
# route file per list there is one description of each
# master here and one set of routes that read from it. The
# url key is the same word the masters screen uses for its
# tabs, so /masters/supplier lines up with the Suppliers tab.
#
# inline    can this master be created in the middle of
#           data entry. Branch cannot.
# has_hs    does this master carry a list of H.S. codes.
#           Only Item does.
#
# WORKS IS NOT HERE, deliberately. Works and Branch are the
# same thing to the business — the imports sheet's "Works"
# column is what fills consignments.branch_id — so a separate
# Works master was a duplicate list that held zero rows and
# that nothing referenced. The model and table remain (no DDL
# is run against them); they are simply no longer exposed.
#-----------------------------------------------------

MASTERS = {
    "supplier": {
        "model": Supplier,
        "create_schema": SupplierCreateSchema,
        "update_schema": SupplierUpdateSchema,
        "noun": "supplier",
        "inline": True,
        "has_hs": False,
        # Scalar columns only — the list route's search runs a real SQL ILIKE
        # across these, replacing a Python scan over every serialized field.
        "search_fields": ["name", "country", "city", "contact_name", "phone",
                          "email", "default_currency", "default_payment_terms"],
    },
    "customer": {
        "model": Customer,
        "create_schema": CustomerCreateSchema,
        "update_schema": CustomerUpdateSchema,
        "noun": "customer",
        # Inline-creatable, for the same reason Supplier is: the logistics
        # wizard resolves a typed customer name to this master, and a name
        # nobody has entered yet would otherwise block the order from being
        # saved at all.
        "inline": True,
        "has_hs": False,
        "search_fields": ["name"],
    },
    "branch": {
        "model": Branch,
        "create_schema": BranchCreateSchema,
        "update_schema": BranchUpdateSchema,
        "noun": "branch",
        "inline": False,
        "has_hs": False,
        "search_fields": ["name", "code", "city", "address"],
    },
    "port": {
        "model": Port,
        "create_schema": PortCreateSchema,
        "update_schema": PortUpdateSchema,
        "noun": "port",
        "inline": True,
        "has_hs": False,
        "search_fields": ["name", "country", "port_type", "un_locode"],
    },
    "agent": {
        "model": ClearingAgent,
        "create_schema": ClearingAgentCreateSchema,
        "update_schema": ClearingAgentUpdateSchema,
        "noun": "clearing agent",
        "inline": True,
        "has_hs": False,
        "search_fields": ["name", "licence_no", "contact_name", "phone"],
    },
    "transporter": {
        "model": Transporter,
        "create_schema": TransporterCreateSchema,
        "update_schema": TransporterUpdateSchema,
        "noun": "transporter",
        # Inline-creatable, same reason as Customer: the trucking wizard
        # resolves a typed transporter name to this master, and a name nobody
        # has entered yet would otherwise block the job from being saved.
        "inline": True,
        "has_hs": False,
        "search_fields": ["name", "contact_name", "phone", "ntn"],
    },
    "item": {
        "model": Item,
        "create_schema": ItemCreateSchema,
        "update_schema": ItemUpdateSchema,
        "noun": "item",
        "inline": True,
        "has_hs": True,
        "search_fields": ["item_code", "name", "default_specification",
                          "default_unit_of_measurement", "category"],
    },
}

# The order the tabs appear in on the masters screen.
MASTER_ORDER = ["customer", "supplier", "port", "agent", "transporter", "branch", "item"]


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
