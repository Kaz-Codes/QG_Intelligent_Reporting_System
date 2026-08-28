from app.logistics.routes.router import router
from app.notifications.lifecycle import notify_status_changed, notify_completed
from app.logistics.helpers import order_reference
from app.enums import LogisticsStatus
from app.logistics.schemas import LogisticsConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_LOGISTICS
from app.logistics.helpers import (
    updated_fields, apply_updates,
    new_children_to_add, updated_children, delete_missing,
    add_in_consignment_change_history, add_in_status_change_history,
    create_child_objects, fetch_consignment, resolve_customer_id,
    stamp_trucking_handoff,
)
from app.logistics.models import LogisticsItem, LogisticsPackage, LogisticsContainer
from app.logistics.serializers import serialize_consignment, serialize_many
import logging

logger = logging.getLogger(__name__)

#---------------------------------------
# THE LIFECYCLE STATUS EVENT
#
# Fires on the CHANGE, not on the save: updation_dict only carries a field the
# diff engine found actually different, so a wizard step posting the whole
# draft back with an unchanged status produces nothing.
#
# COMPLETION SUPPRESSES THE PAIRED STATUS CHANGE — reaching "Delivered" IS a
# status change, and emitting both would say the same thing twice, one line
# apart. The completion is the more informative, so it is emitted instead.
#---------------------------------------

def _notify_status_lifecycle(db, updation_dict, consignment):
    try:
        change = updation_dict.get("current_status")

        if not change:
            return

        old_status = change.get("old_value")
        new_status = change.get("new_value")

        if not new_status or old_status == new_status:
            return

        reference = order_reference(consignment)
        party = consignment.customer_name or "unknown customer"

        if new_status == LogisticsStatus.DELIVERED.value:
            notify_completed(
                db, "logistics", consignment.id,
                reference=reference, party=party, status=new_status,
            )
            return

        notify_status_changed(
            db, "logistics", consignment.id,
            reference=reference,
            old_status=old_status,
            new_status=new_status,
        )

    except Exception:
        logger.exception(
            "Could not raise the lifecycle notification for order %s — "
            "swallowed; the update itself is already committed",
            getattr(consignment, "id", None),
        )


@router.put("/{consignment_id}")
def update_consignment(
        consignment_data : LogisticsConsignmentSchema,
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_EDIT_LOGISTICS, db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        # A closed order (status reached "Delivered") is locked for everyone
        # until an admin reopens it.
        if consignment.is_locked:
            raise HTTPException(
                status_code=423,
                detail="This order is closed. An admin must reopen it before it can be edited."
            )

        # Header field diff
        updation_dict = updated_fields(consignment, consignment_data, db)

        # New lines (no id yet)
        new_items = new_children_to_add(consignment_data.items)
        new_packages = new_children_to_add(consignment_data.packages)
        new_containers = new_children_to_add(consignment_data.containers)

        # Field level diff for lines that already exist
        item_updates = updated_children(consignment.items, consignment_data.items)
        package_updates = updated_children(consignment.packages, consignment_data.packages)
        container_updates = updated_children(consignment.containers, consignment_data.containers)

        # Lines the user removed (present in db, missing from the request)
        present_item_ids = [i.id for i in (consignment_data.items or []) if i.id is not None]
        present_package_ids = [p.id for p in (consignment_data.packages or []) if p.id is not None]
        present_container_ids = [c.id for c in (consignment_data.containers or []) if c.id is not None]

        deleted_items = delete_missing(consignment, present_item_ids, LogisticsItem.id, db, LogisticsItem)
        deleted_packages = delete_missing(consignment, present_package_ids, LogisticsPackage.id, db, LogisticsPackage)
        deleted_containers = delete_missing(consignment, present_container_ids, LogisticsContainer.id, db, LogisticsContainer)

        # Adding the new lines
        created_items = create_child_objects(new_items, LogisticsItem)
        created_packages = create_child_objects(new_packages, LogisticsPackage)
        created_containers = create_child_objects(new_containers, LogisticsContainer)

        for item in created_items:
            consignment.items.append(item)
        for package in created_packages:
            consignment.packages.append(package)
        for container in created_containers:
            consignment.containers.append(container)

        db.flush()

        # Recording the change so it can be reverted
        add_in_consignment_change_history(
            updation_dict,
            serialize_many(created_items), serialize_many(created_packages), serialize_many(created_containers),
            deleted_items, deleted_packages, deleted_containers,
            item_updates, package_updates, container_updates,
            consignment, user, db
        )

        add_in_status_change_history(updation_dict, consignment, user, db)

        # Applying header updates
        apply_updates(updation_dict, consignment)

        # sent_to_trucking is one of the header fields apply_updates just set;
        # this stamps its companion timestamp when it just turned true.
        stamp_trucking_handoff(updation_dict, consignment)

        # Re-derive the master link AFTER the header updates, so a changed
        # customer name moves customer_id with it.
        resolve_customer_id(consignment, db)

        # A plain draft save never closes an order, even if this update sets
        # the status to "Delivered" on an already-submitted record —
        # submission is what closes it (see submit_consignment.py), not merely
        # saving while both conditions happen to be true. Only /submit locks.
        # Mirrors imports.

        # Applying line updates
        items_map = {item.id: item for item in consignment.items}
        packages_map = {package.id: package for package in consignment.packages}
        containers_map = {container.id: container for container in consignment.containers}

        for updated_item in item_updates:
            row = items_map.get(updated_item.get("id"))
            if row:
                apply_updates(updated_item, row)

        for updated_package in package_updates:
            row = packages_map.get(updated_package.get("id"))
            if row:
                apply_updates(updated_package, row)

        for updated_container in container_updates:
            row = containers_map.get(updated_container.get("id"))
            if row:
                apply_updates(updated_container, row)

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        # AFTER the commit — see the note on the function.
        _notify_status_lifecycle(db, updation_dict, consignment)

        return {
            "status_code":200,
            "detail":"Order updated",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.update_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
