from app.imports.helpers import fetch_consignment
from sqlalchemy.inspection import inspect


#---------------------------------------
# CONVERT SQL ALCHEMY MODEL OBJECTS
# INTO PYTHON DICTIONARIES THAT 
# THAT CAN BE SENT IN RESPONSE
#---------------------------------------

def serialize_consignment(consignment, db):
    saved_consignment = fetch_consignment(db, consignment.id)

    return {
        "id" : saved_consignment.id,
        "branch" : serialize_master(saved_consignment.branch),
        "supplier" : serialize_master(saved_consignment.supplier),
        "works" : serialize_master(saved_consignment.works),
        "clearing_agent" : serialize_master(saved_consignment.clearing_agent),
        "loading_port" : serialize_master(saved_consignment.loading_port),
        "delivery_port" : serialize_master(saved_consignment.delivery_port),

        "items" : serialize_many(saved_consignment.items),
        "eta_revisions" : serialize_many(saved_consignment.eta_revisions),
        "status_updates" : serialize_many(saved_consignment.status_updates),
        "change_history" : serialize_many(saved_consignment.change_history),
        "payments" : serialize_many(saved_consignment.payments),

        "created_by" : saved_consignment.created_by.username if saved_consignment.created_by else None,
        "created_by_id" : saved_consignment.created_by_id if saved_consignment.created_by_id else None,

        "origin" : saved_consignment.origin,
        "currency" : saved_consignment.currency,
        "consignment_type" : saved_consignment.consignment_type,
        "mode_of_shipment" : saved_consignment.mode_of_shipment,
        "etd" : saved_consignment.etd,
        "eta" : saved_consignment.eta,
        "eta_works" : saved_consignment.eta_works,
        "cargo_readiness_date" : saved_consignment.cargo_readiness_date,
        "payment_instrument" : saved_consignment.payment_instrument,
        "instrument_number" : saved_consignment.instrument_number,
        "opening_or_retirement_date" : saved_consignment.opening_or_retirement_date,
        "exchange_rate" : saved_consignment.exchange_rate,
        "rate_booked_on" : saved_consignment.rate_booked_on,
        "rate_source" : saved_consignment.rate_source,
        "current_status" : saved_consignment.current_status,
        "effective_date" : saved_consignment.effective_date,
        "remarks" : saved_consignment.remarks,
        "gd_number" : saved_consignment.gd_number,
        "gd_filing_date" : saved_consignment.gd_filing_date,
        "free_days_allowed" : saved_consignment.free_days_allowed,
        "gate_out_date" : saved_consignment.gate_out_date,
        "demurrage_or_detention_paid" : saved_consignment.demurrage_or_detention_paid,

        "is_deleted" : saved_consignment.is_deleted,
        "deleted_at" : saved_consignment.deleted_at,
        "deleted_by_id" : saved_consignment.deleted_by_id if saved_consignment.deleted_by_id else None,
        "deleted_by" : saved_consignment.deleted_by.username if saved_consignment.deleted_by else None
    }

#---------------------------------------------
# A SINGLE DYNAMIC FUNCTION THAT
# CAN SERIALIZE ALL THE MASTER TABLES MODELS
#---------------------------------------------

def serialize_master(master):
    master_dict = (
        {
            column.key : getattr(master, column.key)
            for column in inspect(master).mapper.column_attrs
        }
        if master
        else
        None
    )

    return master_dict

#---------------------------------------------
# SERIALIZE MODELS THAT ARE A COLLECTION
#---------------------------------------------

def serialize_many(models_list):
    serialized_models = []

    for model in models_list:
        serialized_models.append(
            {
                column.key : getattr(model, column.key)
                for column in inspect(model).mapper.column_attrs
            }
        )

    return serialized_models


#----------------------------------
# SERIALIZE CONSIGNMENT HISTORY
#----------------------------------

def serialize_consignment_history(consignment_history):
    return {
        "id":consignment_history.id,
        "consignment_id":consignment_history.consignment_id,
        "change_type":consignment_history.change_type,
        "history":consignment_history.history,
        "changed_by_id":consignment_history.changed_by_id,
        "changed_by":consignment_history.changed_by.username if consignment_history.changed_by else None,

        "is_reverted":consignment_history.is_reverted,
        "reverted_by_id":consignment_history.reverted_by_id,
        "reverted_by":consignment_history.reverted_by.username if consignment_history.reverted_by else None,

        "reverted_at":consignment_history.reverted_at,
        "is_revert":consignment_history.is_revert
    }