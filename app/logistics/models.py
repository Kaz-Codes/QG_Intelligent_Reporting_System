from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from app.database import Base
from app.models_mixins import TimestampMixin

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Only used inside the quoted "User" annotations, which SQLAlchemy resolves
# from its registry. Imported for the type checker only, the same way the
# imports module references accounts.
if TYPE_CHECKING:
    from app.accounts.models import User

#-----------------------------------------------------
# THE LOGISTICS TABLES
#
# Shape of the data, kept deliberately close to the imports module:
#
#     LogisticsConsignment              one export or local order
#       |
#       +-- LogisticsStatusHistory      a log of every status change
#       +-- LogisticsChangeHistory      what a field was before it changed
#
# A logistics order is flatter than an import. It carries one item detail,
# one customer and a fixed set of expenditure figures, so there is no
# repeating item or payment child table the way imports has. Everything a
# step captures sits on the order itself.
#
# Two rules carried over from imports:
#
# 1. Money and weights are always Numeric, never Float.
#
# 2. Nothing is ever really deleted. Deleting only sets a flag, so the
#    order and its history stay and can be put back.
#-----------------------------------------------------


#--------------------------------
# LOGISTICS CONSIGNMENTS TABLE
#--------------------------------

class LogisticsConsignment(Base, TimestampMixin):
    __tablename__ = "logistics_consignments"

    id: Mapped[int] = mapped_column(primary_key=True)

    #--- step 1: order ---
    # Export or Local. Drives which of the origin fields and which
    # expenditures apply, so it lives on the order.
    order_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    # Origin is a country for exports, and city + province for local orders.
    # All three are kept; the front end fills the pair that matches.
    origin_country: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    origin_city: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    origin_province: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    customer_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    item_detail: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    net_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    gross_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    # IDM is captured for every order. Export orders also carry an export no.
    idm: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    export_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    batch_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    #--- step 2: transportation ---
    # delay days (gate out - dispatch note) and rate per weight
    # (actual freight / gross weight) are worked out on the front end and
    # never stored, the same way transit time is handled in imports.
    transporter_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    vehicle_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    gate_out_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    dispatch_note_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    quoted_freight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    actual_freight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    actual_delivery_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    origin_factory: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    destination: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    #--- step 3: shipping ---
    container_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    container_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    # Port of loading and port of discharge
    pol: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    pod: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    shipping_line: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    clearing_agent: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    booking_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    port_in_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    etd_sailing_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    cro_arrival_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    actual_arrival_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    #--- step 4: expenditures ---
    # A fixed set of named costs. The export set is the full list; local
    # orders only use packing cost and transportation charges. The total
    # and the cost per kg are worked out on the front end, never stored.
    packing_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    transportation_charges: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    insurance: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    trucking_lhr_to_khi: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    fumigation_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    lashing: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    qfl_charges: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    qfl_container_movement: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    custom_clearance_charges: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    port_charges: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    dhl_charges: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    sea_air_freight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    #--- step 5: status ---
    current_status: Mapped[str] = mapped_column(
        String(50),
        default="Under Production",
        nullable=False,
        index=True
    )

    # The day the stage actually changed, mirroring imports. The status
    # history counts stage ageing from this.
    effective_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        index=True
    )

    remarks: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    #--- who made it ---
    # A creator is always required. RESTRICT stops a user row being deleted
    # while it still owns orders.
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )

    # Deleting only sets this flag. The row stays, so it can be put back.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    #--- links to the user who touched it ---
    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id]
    )

    deleted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[deleted_by_id]
    )

    #--- everything that hangs off an order ---
    status_updates: Mapped[list["LogisticsStatusHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    change_history: Mapped[list["LogisticsChangeHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )


#--------------------------------
# LOGISTICS STATUS HISTORY TABLE
#
# effective_date is the day the stage actually changed, which is often not
# the day somebody got round to entering it.
#--------------------------------

class LogisticsStatusHistory(Base, TimestampMixin):
    __tablename__ = "logistics_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("logistics_consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    previous_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    new_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True
    )

    remarks: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    consignment: Mapped["LogisticsConsignment"] = relationship(
        back_populates="status_updates"
    )

    user: Mapped[Optional["User"]] = relationship()


#--------------------------------
# LOGISTICS CHANGE HISTORY TABLE
#
# One row per update, holding the values as they were before the change.
# That is what makes reverting possible. Only the fields that actually
# changed are stored, not the whole record.
#--------------------------------

class LogisticsChangeHistory(Base, TimestampMixin):
    __tablename__ = "logistics_change_history"
    __table_args__ = (
        Index("ix_logistics_change_history_consignment", "consignment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("logistics_consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    change_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    history: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False
    )

    changed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Set once this change has been undone, so it cannot be undone twice
    is_reverted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    reverted_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    reverted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # True when this row was itself created by a revert.
    is_revert: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    consignment: Mapped["LogisticsConsignment"] = relationship(
        back_populates="change_history"
    )

    changed_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[changed_by_id]
    )

    reverted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[reverted_by_id]
    )
