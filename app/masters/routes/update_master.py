from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import (
    check_unique, get_row, parse_payload, set_hs_codes, used_counts,
)
from app.auth.authorize_user import authorize
from app.masters.registry import get_master_config
from app.masters.routes.router import router
from app.masters.serializers import serialize
from fastapi import Request, HTTPException

#-------------------------------------------
# EDIT A MASTER RECORD (ADMIN, MANAGER)
#
# Only what the user changed is sent, so a
# field left out keeps its current value
# rather than being blanked.
#
# A Manager opening and saving a record that
# was created inline is the review step
# itself. Once they have looked at it and
# saved, it is confirmed, so an unverified
# record becomes verified here.
#-------------------------------------------

@router.put("/{master}/{row_id}")
async def update_master(master : str, row_id : int, payload : dict, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin", "manager"], db)

        config = get_master_config(master)
        model = config["model"]

        row = get_row(model, row_id, db)
        data = parse_payload(config["update_schema"], payload)

        sent = data.model_dump(exclude_unset=True)

        if "name" in sent:
            check_unique(model, "name", sent["name"], db, ignore_id=row.id)

        if config["has_hs"] and "item_code" in sent:
            check_unique(model, "item_code", sent["item_code"], db, ignore_id=row.id)

        for field, value in sent.items():
            if field == "hs_codes":
                continue

            setattr(row, field, value)

        # None means the caller did not touch the codes at
        # all. A list, even an empty one, is a deliberate set.
        if config["has_hs"] and sent.get("hs_codes") is not None:
            set_hs_codes(row, sent["hs_codes"], db)

        # A manager saving an inline-created record is what
        # confirms it.
        if not row.is_verified:
            row.is_verified = True

        db.commit()
        db.refresh(row)

        counts = used_counts(master, [row.id], db)

        return {
            "status": 200,
            "message": "Record updated",
            "data": serialize(master, row, counts.get(row.id, 0))
        }

    except HTTPException:
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
