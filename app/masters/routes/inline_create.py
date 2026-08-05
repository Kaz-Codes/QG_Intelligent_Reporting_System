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
# ADD A MASTER IN THE MIDDLE OF DATA ENTRY
# (ADMIN, MANAGER, ENTRY OPERATOR)
#
# When somebody typing up a consignment names
# a Supplier, Item, Port or Clearing Agent
# that does not exist yet, this appends it to
# the master without making them leave the
# wizard.
#
# The one difference from a normal create is
# that it lands with is_verified false. It
# then shows up in the Masters review queue
# until a Manager or Admin opens and saves it,
# confirming the details are right.
#
# Branch and Works refuse this on purpose.
# They are our own entities and must be set up
# deliberately, never typed into existence
# mid consignment.
#-------------------------------------------

@router.post("/{master}/inline")
async def inline_create(master : str, payload : dict, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_ADD_MASTER, db)

        config = get_master_config(master)

        if not config["inline"]:
            raise HTTPException(
                status_code=403,
                detail="This master cannot be created during data entry"
            )

        model = config["model"]
        data = parse_payload(config["create_schema"], payload)

        check_unique(model, "name", data.name, db)

        if config["has_hs"]:
            check_unique(model, "item_code", data.item_code, db)

        fields = data.model_dump(exclude={"hs_codes"})

        record = model(**fields)
        record.is_verified = False

        db.add(record)
        db.flush()

        if config["has_hs"]:
            set_hs_codes(record, data.hs_codes, db)

        db.commit()
        db.refresh(record)

        counts = used_counts(master, [record.id], db)

        return {
            "status": 201,
            "message": "Record created, pending review",
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
