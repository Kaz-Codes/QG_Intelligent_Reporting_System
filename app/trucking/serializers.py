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

    # The named gaps that stop this job being submitted — the same rule set
    # /submit enforces, so a disabled Submit and a failed submit can't
    # disagree. Loaded rows are all still drafts and legitimately incomplete,
    # so this is usually non-empty for them.
    #
    # Imported inside the function: helpers imports this module for
    # serialize_many, so a module-level import would be circular — the very
    # cycle this file's header says trucking avoids.
    from app.trucking.helpers import submission_errors
    data["missing_fields"] = submission_errors(consignment)

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
        # When the change was made (TimestampMixin). The history screen orders
        # and dates every card by this, so it has to go out with the row.
        "changed_at": consignment_history.created_at,

        "is_reverted": consignment_history.is_reverted,
        "reverted_by_id": consignment_history.reverted_by_id,
        "reverted_by": consignment_history.reverted_by.username if consignment_history.reverted_by else None,

        "reverted_at": consignment_history.reverted_at,
        "is_revert": consignment_history.is_revert
    }
