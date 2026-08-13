#-----------------------------------------------------
# TURNING MASTER ROWS INTO JSON
#
# Each master sends back exactly the columns its screen
# shows, plus the "used in" count worked out separately and
# passed in. is_active and is_verified come back on every
# one so the screen can grey out inactive rows and flag the
# ones still waiting for review.
#-----------------------------------------------------


def serialize_supplier(row, used=0):
    return {
        "id": row.id,
        "name": row.name,
        "country": row.country,
        "city": row.city,
        "contact_name": row.contact_name,
        "phone": row.phone,
        "email": row.email,
        "default_currency": row.default_currency,
        "default_payment_terms": row.default_payment_terms,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_branch(row, used=0):
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "city": row.city,
        "address": row.address,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_works(row, used=0):
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "ntn_strn": row.ntn_strn,
        "note": row.note,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_customer(row, used=0):
    # Name only — see the model. `used` is how many logistics orders point at
    # this customer, so nobody deactivates one still being shipped to.
    return {
        "id": row.id,
        "name": row.name,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_port(row, used=0):
    return {
        "id": row.id,
        "name": row.name,
        "country": row.country,
        "port_type": row.port_type,
        "un_locode": row.un_locode,
        "used_as": row.used_as,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_agent(row, used=0):
    return {
        "id": row.id,
        "name": row.name,
        "licence_no": row.licence_no,
        "contact_name": row.contact_name,
        "phone": row.phone,
        "primary_port_id": row.primary_port_id,
        "primary_port": {
            "id": row.primary_port.id,
            "name": row.primary_port.name
        } if row.primary_port else None,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_transporter(row, used=0):
    return {
        "id": row.id,
        "name": row.name,
        "contact_name": row.contact_name,
        "phone": row.phone,
        "ntn": row.ntn,
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


def serialize_item(row, used=0):
    return {
        "id": row.id,
        "item_code": row.item_code,
        "name": row.name,
        "default_specification": row.default_specification,
        "default_unit_of_measurement": row.default_unit_of_measurement,
        "category": row.category,
        "hs_codes": [code.code for code in row.hs_codes if code.is_active],
        "is_active": row.is_active,
        "is_verified": row.is_verified,
        "used": used,
    }


#--------------------------------
# AN ITEM AS THE WIZARD TYPEAHEAD NEEDS IT
#
# Just the fields the consignment form auto-fills when an
# item is picked, kept light because this is a live search.
# The used count, verified flag and active flag are left off
# on purpose, they are not needed to fill the form.
#--------------------------------

def serialize_item_for_entry(item):
    return {
        "id": item.id,
        "item_code": item.item_code,
        "name": item.name,
        "default_specification": item.default_specification,
        "default_unit_of_measurement": item.default_unit_of_measurement,
        "category": item.category,
        "hs_codes": [code.code for code in item.hs_codes if code.is_active]
    }


#--------------------------------
# ONE ENTRY POINT, SO THE ROUTES DO NOT EACH
# HOLD A MAP OF MASTER TO SERIALIZER
#--------------------------------

SERIALIZERS = {
    "supplier": serialize_supplier,
    "customer": serialize_customer,
    "branch": serialize_branch,
    "port": serialize_port,
    "agent": serialize_agent,
    "transporter": serialize_transporter,
    "item": serialize_item,
    # "works" is gone: Works and Branch are the same thing to the business (the
    # imports sheet's "Works" column fills branch_id), the table holds no rows
    # and nothing references it. serialize_works is kept just below in case a
    # database somewhere still has the table.
}


def serialize(master, row, used=0):
    return SERIALIZERS[master](row, used)
