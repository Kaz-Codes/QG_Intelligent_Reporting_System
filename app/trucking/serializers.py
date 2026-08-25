from sqlalchemy.inspection import inspect

from app.enums import VehicleTrackingStatus


#----------------------------------------
# AUTO-GENERATED SYSTEM REMARKS
#
# Mirrors app/imports/serializers.py::build_system_remarks — derived on read,
# never stored, never accepted from the client, so a user edit can't wipe it
# and it is always current.
#
# Trucking has NEITHER an ETA-revision table NOR a status-history table —
# unlike imports/logistics there is no stored job-level status at all (see
# the module docstring in models.py): each vehicle carries its own
# tracking_status, with no log of its past values, only the current one. So
# there is no "status changed on date X" sentence to build here; instead this
# states the hand-off this job was taken from (source/source_ref/taken_at)
# and a same-instant rollup of the vehicles' CURRENT tracking statuses — the
# only "status" data this module actually keeps.
#----------------------------------------

_SOURCE_LABELS = {
    "from-logistics": "a Logistics order",
    "from-import-fob": "an Import FOB consignment",
    "from-export": "an Export order",
}


def build_system_remarks(consignment):
    parts = []

    # Where the job came from, if taken from an open request.
    if consignment.source and consignment.source != "manual" and consignment.source_ref:
        label = _SOURCE_LABELS.get(consignment.source, consignment.source)
        if consignment.taken_at:
            parts.append(f"Taken from {label} {consignment.source_ref} on {consignment.taken_at:%Y-%m-%d}.")
        else:
            parts.append(f"Taken from {label} {consignment.source_ref}.")

    # Current tracking status per vehicle — the only "status" trucking keeps;
    # there is no history of past values to chain, only today's snapshot.
    active_vehicles = [v for v in consignment.vehicles if not v.is_deleted]
    if active_vehicles:
        order = [s.value for s in VehicleTrackingStatus]
        counts = {}
        for vehicle in active_vehicles:
            counts[vehicle.tracking_status] = counts.get(vehicle.tracking_status, 0) + 1
        total = len(active_vehicles)

        if len(counts) == 1:
            status = next(iter(counts))
            parts.append(f"All {total} vehicle{'s' if total != 1 else ''} {status.lower()}.")
        else:
            ordered_statuses = [s for s in order if s in counts] + [s for s in counts if s not in order]
            breakdown = ", ".join(f"{counts[s]} {s.lower()}" for s in ordered_statuses)
            parts.append(f"{total} vehicles — {breakdown}.")

    if consignment.dispatch_note_date:
        parts.append(f"Dispatch note issued {consignment.dispatch_note_date}.")

    if consignment.eta_works:
        parts.append(f"ETA works {consignment.eta_works}.")

    return " ".join(parts)


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
    data["system_remarks"] = build_system_remarks(consignment)

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
