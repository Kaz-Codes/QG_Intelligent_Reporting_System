from sqlalchemy.inspection import inspect


#---------------------------------------
# CONVERT SQL ALCHEMY MODEL OBJECTS
# INTO PYTHON DICTIONARIES THAT
# CAN BE SENT IN RESPONSE
#
# The imports serializer re-fetches the row inside itself, which is what
# ties its serializer and helpers into a circular import. Here the routes
# already hand over a freshly fetched, fully loaded order, so the serializer
# just reads it. No re-fetch, no cycle.
#---------------------------------------

def serialize_consignment(consignment):
    data = {
        column.key: getattr(consignment, column.key)
        for column in inspect(consignment).mapper.column_attrs
    }

    data["items"] = serialize_many(consignment.items)
    data["packages"] = serialize_many(consignment.packages)
    data["containers"] = serialize_many(consignment.containers)
    data["status_updates"] = serialize_many(consignment.status_updates)
    data["change_history"] = serialize_many(consignment.change_history)

    data["created_by"] = consignment.created_by.username if consignment.created_by else None
    data["deleted_by"] = consignment.deleted_by.username if consignment.deleted_by else None

    # The named gaps that stop this order being submitted — the same rule set
    # /submit enforces, so the list's "Draft" badge, a disabled Submit button
    # and a failed submit can never disagree. Loaded (Excel) rows are all still
    # drafts and legitimately incomplete, so this is usually non-empty for them.
    #
    # Imported inside the function on purpose: helpers imports this module for
    # serialize_many, so a module-level import would be circular — the exact
    # cycle this file's header comment says it avoids.
    from app.logistics.helpers import submission_errors
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
# SERIALIZE CONSIGNMENT HISTORY
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
