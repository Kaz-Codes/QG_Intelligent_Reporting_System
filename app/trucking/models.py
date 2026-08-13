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
# imports and logistics modules reference accounts.
if TYPE_CHECKING:
    from app.accounts.models import User
    from app.masters.models import Transporter

#-----------------------------------------------------
# THE TRUCKING TABLES
#
# Shape of the data, kept close to the imports module:
#
#     TruckingConsignment              one trucking job
#       |
#       +-- TruckingVehicle            the trucks it moves on
#       +-- TruckingChangeHistory      what a field was before it changed
#
# The one thing that sets trucking apart, and the reason it follows imports
# rather than logistics, is the header plus repeating vehicle rows. One job
# can move on several trucks, and a number of fields vary per truck, so the
# vehicles sit on their own line the same way item lines sit under a
# consignment.
#
# There is no stored consignment level status. Each truck carries its own
# tracking status, and the job level status is a rollup over the trucks that
# the front end works out. Nothing calculates it here.
#-----------------------------------------------------


#--------------------------------
# TRUCKING CONSIGNMENTS TABLE
#--------------------------------

class TruckingConsignment(Base, TimestampMixin):
    __tablename__ = "trucking_consignments"

    id: Mapped[int] = mapped_column(primary_key=True)

    #--- step 1: movement and item ---
    # Intrafactory, Outbound or Inbound. Drives which fields apply on
    # several steps, so it lives on the job.
    movement_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    # Where the job came from: manual, from-logistics, from-import-fob or
    # from-export.
    source: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True
    )

    # Set only when the job was created by a "Take Action" on an open
    # request. A point-in-time reference to the originating record ("taken
    # from order X"), never a live pointer — later changes to that record do
    # not flow through.
    source_ref: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    # ISO datetime the operator clicked Take Action.
    taken_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Snapshot of the source's items/packages at the moment of taking, used
    # only to pre-fill the form. A list of
    # {source_package_id, label, item_details, quantity, weight}.
    taken_snapshot: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )

    execution_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    transporter_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # The master link, kept in step with transporter_name by
    # helpers.resolve_transporter_id on every create, update and revert — the
    # wizard still sends a typed name, this is derived from it. A name
    # matching no transporter leaves this NULL rather than minting a master
    # row from a typo. Mirrors LogisticsConsignment.customer_id.
    transporter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transporters.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    transporter: Mapped[Optional["Transporter"]] = relationship(
        back_populates="trucking_jobs"
    )

    shifting_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    item_details: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    # A factory for intrafactory movements, free text otherwise.
    pickup: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    destination: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Shipment reference / IDM, for outbound and inbound movements.
    reference_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    #--- step 3: freight and payment ---
    # savings (quoted - actual), rate per kg and outstanding are worked out
    # on the front end and never stored.
    quoted_freight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    actual_freight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    payment_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    paid_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    # Vehicle / container detention cost.
    detention: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    #--- step 4: tracking ---
    dispatch_note_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    eta_works: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    remarks: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    # Draft vs submitted. Optional, opt-in from the front end: a draft saves
    # with anything filled (the normal create/update); submitting runs the
    # rule set (helpers.submission_errors) and only then flips this to
    # "submitted". Submitting never locks the job. server_default so rows
    # written straight to the table come in as drafts.
    record_state: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        server_default="draft",
        nullable=False,
        index=True
    )

    # The closed lock. A job closes once every one of its vehicles is
    # "Delivered"; from then on nobody may edit it until an admin reopens it.
    # Trucking has no stored job-level status, so "closed" is derived from the
    # vehicles (see helpers.is_closed). Separate from record_state.
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True
    )

    #--- who made it ---
    # A creator is always required. RESTRICT stops a user row being deleted
    # while it still owns jobs.
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

    #--- everything that hangs off a job ---
    vehicles: Mapped[list["TruckingVehicle"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    change_history: Mapped[list["TruckingChangeHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )


#--------------------------------
# TRUCKING VEHICLES TABLE
#
# One row per truck. A number of fields vary truck by truck, which is why
# they sit here and not on the job. Each truck carries its own tracking
# status and advances on its own.
#--------------------------------

class TruckingVehicle(Base, TimestampMixin):
    __tablename__ = "trucking_vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("trucking_consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    vehicle_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    vehicle_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    no_of_packages: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    driver_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
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

    # Import FOB (inbound) only.
    container_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    container_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    tracking_status: Mapped[str] = mapped_column(
        String(20),
        default="Going to load",
        nullable=False
    )

    # Which logistics packages ride on this truck: a list of {package_id}.
    # A package may fill a whole truck or share one with others (many to
    # many), so this is a list, driven by the front end.
    package_refs: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )

    # Which import consignments ride on this truck: a list of
    # {consignment_id}. Two or more imports can move on one vehicle.
    import_consignment_refs: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )

    # A vehicle removed on an update is only flagged, so a revert can put it
    # back, mirroring the item lines in imports.
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

    consignment: Mapped["TruckingConsignment"] = relationship(
        back_populates="vehicles"
    )


#--------------------------------
# TRUCKING CHANGE HISTORY TABLE
#
# One row per update, holding the values as they were before the change.
# That is what makes reverting possible. Only the fields that actually
# changed are stored, not the whole record.
#--------------------------------

class TruckingChangeHistory(Base, TimestampMixin):
    __tablename__ = "trucking_change_history"
    __table_args__ = (
        Index("ix_trucking_change_history_consignment", "consignment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("trucking_consignments.id", ondelete="CASCADE"),
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

    consignment: Mapped["TruckingConsignment"] = relationship(
        back_populates="change_history"
    )

    changed_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[changed_by_id]
    )

    reverted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[reverted_by_id]
    )
