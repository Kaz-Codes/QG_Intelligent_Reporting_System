from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.imports.models import Consignment


#-------------------------------------
# FETCH THE CONSIGNMENTS THE IMPORTS
# DASHBOARD IS BUILT FROM
#
# Only live consignments count, a deleted one is not part of
# the picture. Items are loaded up front because the value of
# a consignment is worked out from its item lines, and the
# supplier and branch are loaded so they can be grouped by
# name without a query per row.
#-------------------------------------

def fetch_consignments(db):
    query = select(Consignment).where(
        Consignment.is_deleted == False
    ).options(
        selectinload(Consignment.items),
        joinedload(Consignment.supplier),
        joinedload(Consignment.branch)
    )

    return db.execute(query).scalars().all()
