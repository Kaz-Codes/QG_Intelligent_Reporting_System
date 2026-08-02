from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from app.database import Base
from app.models_mixins import TimestampMixin

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    text,
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
#     LogisticsConsignment              one export or local order (one batch)
#       |
#       +-- LogisticsItem               the things being shipped (per item)
#       +-- LogisticsPackage            the physical packages they go in
#       +-- LogisticsContainer          the containers booked for the order
#       +-- LogisticsStatusHistory      a log of every status change
#       +-- LogisticsChangeHistory      what a field was before it changed
#
# An order is now a header with repeating item, package and container lines,
# the same header + line pattern imports uses. Two collections that hang off
# a line and are always written as a whole from the front end are kept as JSON
# rather than their own tables, so a save is one round trip and a revert is one
# field:
#
#   * a package's per-item allocations (LogisticsPackage.allocations), and
#   * a per-item RFD-date change feed (LogisticsItem.rfd_history), and
#   * the order's remarks feed (LogisticsConsignment.remarks_log).
#
# The MO / batch grouping and cross-batch item sharing are driven by the front
# end; the backend stores what it is given (batch_no, allocation refs) and does
# not itself renumber batches or resolve cross-batch references.
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

    # Cement / Sugar / General. Merged with order_type for the list label.
    department: Mapped[Optional[str]] = mapped_column(
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

    # MO number is a grouping key, not a unique id. Several orders (batches)
    # can share one MO. batch_no is assigned per MO by the front end and kept
    # here as given; batch_label is its renameable display label.
    mo_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    batch_no: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    batch_label: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    incoterm: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True
    )

    #--- step 3: shipping ---
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

    # Container detention — applies to any order with containers.
    container_detention: Mapped[Optional[Decimal]] = mapped_column(
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

    # The day the goods left the works. Transportation is not a logistics
    # step; the order hands off to trucking, and this is the one date the
    # status step keeps for the handoff.
    gate_out_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    # Set once the order has been handed to the trucking module.
    sent_to_trucking: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    # A feed of remark entries: {id, text, authored_by, authored_at, system}.
    # System entries are generated on the front end (e.g. from RFD changes);
    # user entries are typed. Stored whole, so it is one field to read and
    # write.
    remarks_log: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )

    # Draft vs submitted. Optional, opt-in from the front end: a draft saves
    # with anything filled (the normal create/update); submitting runs the
    # rule set (helpers.submission_errors) and only then flips this to
    # "submitted". Submitting never locks the order. server_default so rows
    # written straight to the table come in as drafts.
    record_state: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        server_default="draft",
        nullable=False,
        index=True
    )

    # The closed lock. An order closes when its status reaches "Delivered";
    # from then on nobody may edit it until an admin reopens it. Separate from
    # record_state — a submitted order is still editable, a closed one is not.
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True
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
    items: Mapped[list["LogisticsItem"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    packages: Mapped[list["LogisticsPackage"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    containers: Mapped[list["LogisticsContainer"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    status_updates: Mapped[list["LogisticsStatusHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    change_history: Mapped[list["LogisticsChangeHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )


#--------------------------------
# LOGISTICS ITEMS TABLE
#
# One row per item. Net weight (quantity x unit weight) is worked out on the
# front end and never stored. rfd_history is the per-item feed of Planned /
# Actual RFD date changes, kept whole as JSON.
#--------------------------------

class LogisticsItem(Base, TimestampMixin):
    __tablename__ = "logistics_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("logistics_consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    job_no: Mapped[Optional[str]] = mapped_column(
        String(100),
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

    unit_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    gross_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    planned_rfd_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    actual_rfd_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    # Feed of {id, field, previous_value, new_value, changed_by, changed_at,
    # remark}. Written whole from the front end.
    rfd_history: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )

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

    consignment: Mapped["LogisticsConsignment"] = relationship(
        back_populates="items"
    )


#--------------------------------
# LOGISTICS PACKAGES TABLE
#
# One row per physical package. allocations is the per-item quantity placed in
# this package, kept whole as JSON: a list of
# {id, item_id, source_order_id, quantity}. source_order_id lets a package
# reference an item owned by a sibling batch under the same MO — the items are
# shared, not copied, and this reference is what the front end drives.
#--------------------------------

class LogisticsPackage(Base, TimestampMixin):
    __tablename__ = "logistics_packages"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("logistics_consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    colour_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    packing_works: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    packing_ready_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    packing_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    quoted_packing_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    actual_packing_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    gross_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="Packing under manufacturing",
        nullable=False
    )

    allocations: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )

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

    consignment: Mapped["LogisticsConsignment"] = relationship(
        back_populates="packages"
    )


#--------------------------------
# LOGISTICS CONTAINERS TABLE
#
# One row per container booked for the order.
#--------------------------------

class LogisticsContainer(Base, TimestampMixin):
    __tablename__ = "logistics_containers"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("logistics_consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    container_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    container_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

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

    consignment: Mapped["LogisticsConsignment"] = relationship(
        back_populates="containers"
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
