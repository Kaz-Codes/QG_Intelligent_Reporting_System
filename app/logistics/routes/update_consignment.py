from app.logistics.routes.router import router
from app.logistics.schemas import LogisticsConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_LOGISTICS
from app.logistics.helpers import (
    updated_fields, verify_entry_ownership, apply_updates,
    new_children_to_add, updated_children, delete_missing,
    add_in_consignment_change_history, add_in_status_change_history,
    create_child_objects, fetch_consignment, is_closed,
)
from app.logistics.models import LogisticsItem, LogisticsPackage, LogisticsContainer
from app.logistics.serializers import serialize_consignment, serialize_many

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

        verify_entry_ownership(consignment, user, db)

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

        # If this update pushed the status to "Delivered" the order is now
        # closed, so lock it. The closing update itself goes through; only
        # later edits are refused, until an admin reopens.
        if is_closed(consignment):
            consignment.is_locked = True

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

        return {
            "status_code":200,
            "detail":"Order updated",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
