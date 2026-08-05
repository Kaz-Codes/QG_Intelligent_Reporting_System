from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import check_unique, parse_payload, set_hs_codes, used_counts
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_MASTER
from app.masters.registry import get_master_config
from app.masters.routes.router import router
from app.masters.serializers import serialize
from fastapi import Request, HTTPException

#-------------------------------------------
# ADD A MASTER RECORD (ADMIN, MANAGER)
#
# The proper way to add a master, through the
# Masters screen. It lands verified, unlike a
# record created inline during data entry
# which lands unverified and waits for review.
#
# Any master can be added this way, including
# Branch and Works, which is the only way
# those two ever get created.
#
# Names are unique, and items also have a
# unique code, so a clash is caught here with
# a plain message rather than a database error.
#-------------------------------------------

@router.post("/{master}")
async def create_master(master : str, payload : dict, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_ADD_MASTER, db)

        config = get_master_config(master)
        model = config["model"]

        # The body is validated against this master's own
        # create schema. Doing it here rather than in the
        # signature is what lets one route serve all six
        # lists.
        data = parse_payload(config["create_schema"], payload)

        check_unique(model, "name", data.name, db)

        if config["has_hs"]:
            check_unique(model, "item_code", data.item_code, db)

        fields = data.model_dump(exclude={"hs_codes"})

        record = model(**fields)
        record.is_verified = True

        db.add(record)
        db.flush()

        if config["has_hs"]:
            set_hs_codes(record, data.hs_codes, db)

        db.commit()
        db.refresh(record)

        counts = used_counts(master, [record.id], db)

        return {
            "status": 201,
            "message": "Record created",
            "data": serialize(master, record, counts.get(record.id, 0))
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
