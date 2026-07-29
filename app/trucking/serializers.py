from sqlalchemy.inspection import inspect


#---------------------------------------
# CONVERT SQL ALCHEMY MODEL OBJECTS
# INTO PYTHON DICTIONARIES THAT
# CAN BE SENT IN RESPONSE
#
# Self contained on purpose. The routes hand over a freshly fetched, fully
# loaded job, so the serializer just reads it. No re-fetch, so trucking
# never ties its serializer and helpers into a circle.
#---------------------------------------

def serialize_consignment(consignment):
    data = {
        column.key: getattr(consignment, column.key)
        for column in inspect(consignment).mapper.column_attrs
    }

    data["vehicles"] = serialize_many(consignment.vehicles)
    data["change_history"] = serialize_many(consignment.change_history)

    data["created_by"] = consignment.created_by.username if consignment.created_by else None
    data["deleted_by"] = consignment.deleted_by.username if consignment.deleted_by else None

    return data


#---------------------------------------------
# SERIALIZE MODELS THAT ARE A COLLECTION
#---------------------------------------------

def serialize_many(models_list):
    serialized_models = []

    for model in models_list:
        serialized_models.append(
            {
                column.key: getattr(model, column.key)
                for column in inspect(model).mapper.column_attrs
            }
        )

    return serialized_models


#----------------------------------
# SERIALIZE CHANGE HISTORY
#----------------------------------

def serialize_consignment_history(consignment_history):
    return {
        "id": consignment_history.id,
        "consignment_id": consignment_history.consignment_id,
        "change_type": consignment_history.change_type,
        "history": consignment_history.history,
        "changed_by_id": consignment_history.changed_by_id,
        "changed_by": consignment_history.changed_by.username if consignment_history.changed_by else None,

        "is_reverted": consignment_history.is_reverted,
        "reverted_by_id": consignment_history.reverted_by_id,
        "reverted_by": consignment_history.reverted_by.username if consignment_history.reverted_by else None,

        "reverted_at": consignment_history.reverted_at,
        "is_revert": consignment_history.is_revert
    }
