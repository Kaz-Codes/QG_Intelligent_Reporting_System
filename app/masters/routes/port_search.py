from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_MASTER
from app.database import SessionLocal
from app.enums import PortType, PortUsedAs
from app.masters.helpers import search_ports
from app.masters.routes.router import router
from app.masters.serializers import serialize_port_for_entry
from fastapi import Request, HTTPException
from typing import Optional
import logging

logger = logging.getLogger(__name__)

#-------------------------------------------
# SEARCH PORTS FOR THE SHIPPING STEP
# (ADMIN, MANAGER, ENTRY OPERATOR)
#
# The port typeahead on the imports and logistics wizards' shipping steps.
# Mirrors item_search.py exactly — the ports master grew to ~133,000 rows
# from its own dedicated workbook and can no longer be preloaded whole, the
# same reason the item catalogue got its own search endpoint.
#
# port_type / used_as are separate, optional filters (not folded into `q`):
# the imports wizard narrows both before the operator types anything (a sea
# consignment must not offer an airport; the loading field must not offer a
# delivery-only port) — see search_ports for the exact WHERE they add.
#
# Registered before the generic /masters/{master} list, so
# /masters/port-search is not read as a master called "port-search".
#-------------------------------------------

@router.get("/port-search")
def port_search(request: Request,
                q: Optional[str] = None,
                limit: int = 10,
                port_type: Optional[PortType] = None,
                used_as: Optional[PortUsedAs] = None):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_VIEW_MASTER, db)

        # keep the number of suggestions sane
        if limit < 1 or limit > 50:
            limit = 10

        ports = search_ports(db, q, limit, port_type, used_as)

        return {
            "status": 200,
            "message": "Ports fetched",
            "data": [serialize_port_for_entry(port) for port in ports]
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.masters.routes.port_search")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
