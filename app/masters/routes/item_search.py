from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_MASTER
from app.database import SessionLocal
from app.masters.helpers import search_items
from app.masters.routes.router import router
from app.masters.serializers import serialize_item_for_entry
from fastapi import Request, HTTPException
from typing import Optional

#-------------------------------------------
# SEARCH ITEMS FOR THE CONSIGNMENT WIZARD
# (ADMIN, MANAGER, ENTRY OPERATOR)
#
# The item name typeahead on data entry. The
# operator types a name and the matching active
# items come back with their code, default
# specification, default unit and H.S. codes,
# so the form can auto-fill the moment an item
# is picked, without a second call.
#
# Registered before the generic /masters/{master}
# list, so /masters/item-search is not read as a
# master called "item-search".
#-------------------------------------------

@router.get("/item-search")
def item_search(request: Request,
                q: Optional[str] = None,
                limit: int = 10):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_VIEW_MASTER, db)

        # keep the number of suggestions sane
        if limit < 1 or limit > 50:
            limit = 10

        items = search_items(db, q, limit)

        return {
            "status": 200,
            "message": "Items fetched",
            "data": [serialize_item_for_entry(item) for item in items]
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
