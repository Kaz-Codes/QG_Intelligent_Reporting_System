from datetime import date

from sqlalchemy.inspection import inspect


#----------------------------------------
# AUTO-GENERATED SYSTEM REMARKS
#
# Mirrors app/imports/serializers.py::build_system_remarks — derived on read,
# never stored, never accepted from the client, so a user edit can't wipe it
# and it is always current.
#
# Logistics has no ETA-revision table (imports' eta_revisions doesn't exist
# here). The closest equivalent this module actually has is the per-item RFD
# change feed (LogisticsItem.rfd_history — JSON, written whole from the front
# end, one list per item), so that stands in for it. sent_to_trucking is a
# plain bool with no companion timestamp column, so its sentence states the
# fact rather than a date.
#----------------------------------------

_RFD_FIELD_LABELS = {
    "plannedRfdDate": "Planned RFD",
    "actualRfdDate": "Actual RFD",
}


def build_system_remarks(consignment):
    parts = []

    # Current status and when it took effect.
    if consignment.current_status:
        status_rows = sorted(
            consignment.status_updates,
            key=lambda u: (u.effective_date or date.min, u.id),
        )
        latest = status_rows[-1] if status_rows else None
        if latest and latest.effective_date:
            parts.append(f"Currently {consignment.current_status} since {latest.effective_date}.")
        else:
            parts.append(f"Currently {consignment.current_status}.")

    # The one-way hand-off to trucking.
    if consignment.sent_to_trucking:
        parts.append("Handed off to Trucking.")

    # RFD changes across every item, oldest first — the closest thing this
    # module has to imports' ETA revision chain. The front end writes this
    # feed whole (RfdChangeEvent: {id, field, previousValue, newValue,
    # changedBy, changedAt, remark}), so field/date keys arrive camelCase.
    events = []
    for item in consignment.items:
        if item.is_deleted:
            continue
        label = item.item_detail or f"Item {item.id}"
        for event in (item.rfd_history or []):
            if not isinstance(event, dict) or not event.get("newValue"):
                continue
            events.append((event.get("changedAt") or "", label, event))

    for _, label, event in sorted(events, key=lambda e: e[0]):
        field_label = _RFD_FIELD_LABELS.get(event.get("field"), event.get("field") or "RFD")
        previous = event.get("previousValue") or "not set"
        parts.append(f"{label}: {field_label} changed from {previous} to {event['newValue']}.")

    return " ".join(parts)


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

def serialize_consignment(consignment, include_change_history=True):
    data = {
        column.key: getattr(consignment, column.key)
        for column in inspect(consignment).mapper.column_attrs
    }

    data["items"] = serialize_many(consignment.items)
    data["packages"] = serialize_many(consignment.packages)
    data["containers"] = serialize_many(consignment.containers)
    data["status_updates"] = serialize_many(consignment.status_updates)
    data["system_remarks"] = build_system_remarks(consignment)

    # The list screen never renders change history — it has its own
    # /change-history route — so the list route skips it here, and
    # fetch_consignments_page (helpers.py) doesn't eager-load it either.
    # Without both halves of that split, accessing consignment.change_history
    # below would lazy-load one extra query per row on every page of the
    # list. The detail fetch (fetch_consignment) still eager-loads it, so
    # this stays free there.
    if include_change_history:
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
