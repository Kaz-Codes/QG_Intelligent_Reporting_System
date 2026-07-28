from sqlalchemy import select

from app.logistics.models import LogisticsConsignment


#-------------------------------------
# FETCH THE ORDERS THE LOGISTICS
# DASHBOARD IS BUILT FROM
#
# Only live orders count. A logistics order is flat, so
# there are no child rows to load, every figure the
# dashboard needs already sits on the order.
#-------------------------------------

def fetch_consignments(db):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.is_deleted == False
    )

    return db.execute(query).scalars().all()
