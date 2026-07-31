# from app.imports.helpers import fetch_consignment
from sqlalchemy.inspection import inspect


#---------------------------------------
# CONVERT SQL ALCHEMY MODEL OBJECTS
# INTO PYTHON DICTIONARIES THAT 
# THAT CAN BE SENT IN RESPONSE
#---------------------------------------

def serialize_consignment(consignment, db):
    #saved_consignment = fetch_consignment(db, consignment.id)

    return {
        "id" : consignment.id,
        "branch" : serialize_master(consignment.branch),
        "supplier" : serialize_master(consignment.supplier),
        "works" : consignment.works,
        "clearing_agent" : serialize_master(consignment.clearing_agent),
        "loading_port" : serialize_master(consignment.loading_port),
        "delivery_port" : serialize_master(consignment.delivery_port),

        "items" : serialize_many(consignment.items),
        "eta_revisions" : serialize_many(consignment.eta_revisions),
        "status_updates" : serialize_many(consignment.status_updates),
        "change_history" : serialize_many(consignment.change_history),
        "payments" : serialize_many(consignment.payments),

        "created_by" : consignment.created_by.username if consignment.created_by else None,
        "created_by_id" : consignment.created_by_id if consignment.created_by_id else None,

        "origin" : consignment.origin,
        "requisition_date" : consignment.requisition_date,
        "currency" : consignment.currency,
        "consignment_type" : consignment.consignment_type,
        "mode_of_shipment" : consignment.mode_of_shipment,
        "etd" : consignment.etd,
        "eta" : consignment.eta,
        "eta_works" : consignment.eta_works,
        "cargo_readiness_date" : consignment.cargo_readiness_date,
        "payment_instrument" : consignment.payment_instrument,
        "instrument_number" : consignment.instrument_number,
        "opening_or_retirement_date" : consignment.opening_or_retirement_date,
        "exchange_rate" : consignment.exchange_rate,
        "rate_booked_on" : consignment.rate_booked_on,
        "rate_source" : consignment.rate_source,
        "current_status" : consignment.current_status,
        "effective_date" : consignment.effective_date,
        "remarks" : consignment.remarks,
        "gd_number" : consignment.gd_number,
        "gd_filing_date" : consignment.gd_filing_date,
        "free_days_allowed" : consignment.free_days_allowed,
        "gate_out_date" : consignment.gate_out_date,
        "demurrage_or_detention_paid" : consignment.demurrage_or_detention_paid,

        "is_deleted" : consignment.is_deleted,
        "deleted_at" : consignment.deleted_at,
        "deleted_by_id" : consignment.deleted_by_id if consignment.deleted_by_id else None,
        "deleted_by" : consignment.deleted_by.username if consignment.deleted_by else None
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