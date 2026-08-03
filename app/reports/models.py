from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models_mixins import TimestampMixin

if TYPE_CHECKING:
    from app.accounts.models import User


#-----------------------------------------------------
# SAVED REPORTS
#
# A saved report is a re-runnable template for the cross-module report builder:
# which data types it spans, which columns to show, and the filter values it was
# built with (deliberately WITHOUT the date range, which is chosen fresh every
# time it is run). The report data itself is never stored — only the recipe — so
# a saved report always pulls current figures.
#
# On the front end these lived in the browser's localStorage ("until the real
# backend lands"); this table is that backend. Templates are shared: everybody
# who can reach Reports sees the whole list, the same way the front end did.
#
# `types`, `columns` and `filters` are small, whole-value blobs written and read
# as one unit, so they are JSON columns rather than their own tables.
#-----------------------------------------------------

class SavedReport(Base, TimestampMixin):
    __tablename__ = "saved_reports"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    # ["purchases", "imports", "inventory", "logistics"] — the data types this
    # report spans.
    types: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )

    # The report-row keys the user chose to display, in order.
    columns: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )

    # {item, supplier, branch, category, search} — the saved filter values. No
    # date range (chosen at run time).
    filters: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )

    # Deleting only sets this flag, like everything else in the system.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    deleted_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id]
    )

    deleted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[deleted_by_id]
    )
