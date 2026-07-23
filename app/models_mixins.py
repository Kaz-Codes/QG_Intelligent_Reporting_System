from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


#-----------------------------------------------------
# TIMESTAMPS FOR EVERY TABLE
#
# Written once here and mixed into each model, rather than repeating
# two columns thirteen times.
#
# server_default means the database fills created_at, so a row written
# by hand in psql still gets one. onupdate means SQLAlchemy sets
# updated_at on every save.
#-----------------------------------------------------

class TimestampMixin:
    created_at : Mapped[datetime] = mapped_column(
        DateTime(timezone = True),
        server_default = func.now(),
        nullable = False
    )

    updated_at : Mapped[datetime] = mapped_column(
        DateTime(timezone = True),
        server_default = func.now(),
        onupdate = func.now(),
        nullable = False
    )