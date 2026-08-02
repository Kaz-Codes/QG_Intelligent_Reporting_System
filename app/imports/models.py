from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from app.database import Base
from app.models_mixins import TimestampMixin

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    text,
)
from sqlalchemy.orm import (
    Mapped, mapped_column, relationship, declarative_mixin,
)

# These names are only used inside quoted "Mapped[...]" annotations, which
# SQLAlchemy resolves from its own class registry at mapper-configuration time.
# Importing them for real would make imports.models and masters.models import
# each other in a circle, so they are pulled in for the type checker only. User
# lives in accounts, not masters.
if TYPE_CHECKING:
    from app.masters.models import Branch, Supplier, Port, ClearingAgent, Item
    from app.accounts.models import User

#-----------------------------------------------------
# THE MAIN TABLES
#
# Shape of the data:
#
#     Consignment                     one shipment from one supplier
#       |
#       +-- ConsignmentItem           the things being imported
#       +-- Payment                   money paid; several is normal
#       +-- EtaRevisionHistory        a log of every ETA change
#       +-- StatusUpdateHistory       a log of every status change
#       +-- ConsignmentChangeHistory  what a field was before it changed
#
# Two rules that matter a lot:
#
# 1. Money is always Numeric, never Float. Floats lose fractions of a
#    rupee, and those add up to a figure finance cannot reconcile.
#
# 2. The exchange rate is saved ON the consignment along with the date
#    it was taken. An old consignment is never re-converted at today's
#    rate, or the same record would show a different PKR figure every
#    time somebody opened it.
#-----------------------------------------------------


#--------------------------------
# CONSIGNMENTS TABLE
#--------------------------------

class Consignment(Base, TimestampMixin):
    __tablename__ = "consignments"

    id: Mapped[int] = mapped_column(primary_key=True)

    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True
    )

    supplier_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True
    )

    requisition_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    # Works is typed in by hand, not picked from a master, so it is free
    # text rather than a foreign key. The sheet's "Works" column is the
    # branch and fills branch_id above.
    works: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    clearing_agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clearing_agents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Both start as copies of the supplier's values and can be changed here
    origin: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    currency: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True
    )

    consignment_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    # FOB feeds the trucking module's import-FOB request derivation.
    incoterm: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True
    )

    po_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    # The day the requisition/indent was raised — before a supplier or PO
    # exists. The gap to po_date is procurement lead time.
    requisition_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    # The day the business actually needs the goods. Delay is measured
    # against this, not a target the system enforces.
    required_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    mode_of_shipment: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    cargo_readiness_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    etd: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    eta: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    eta_works: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    #--- finance ---
    payment_instrument: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    instrument_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    opening_or_retirement_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    exchange_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6),
        nullable=True
    )

    rate_booked_on: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    rate_source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    # Derived, but STORED (recompute_derived, run on every save). foreign_total
    # is the sum of the line totals; pkr_total is that at the booked exchange
    # rate. The PKR figure is stored, not recomputed on read, so a later rate
    # change or edit can never silently restate what a printed report showed.
    foreign_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4),
        nullable=True
    )

    pkr_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2),
        nullable=True
    )

    #--- status ---
    current_status: Mapped[str] = mapped_column(
        String(50),
        default="TT/LC in Process",
        nullable=False,
        index=True
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=True,
        index=True
    )
    
    remarks: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    #--- custom clearance ---
    gd_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    gd_filing_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    free_days_allowed: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    gate_out_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    demurrage_or_detention_paid: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    # Container detention — separate from port demurrage above. PKR.
    container_detention: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    #--- shipping ---
    loading_port_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ports.id", ondelete="SET NULL"),
        nullable=True
    )

    delivery_port_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ports.id", ondelete="SET NULL"),
        nullable=True
    )

    # Draft vs submitted. A draft saves with anything (or nothing) filled;
    # submitting runs the full rule set (see helpers.submission_errors) and,
    # only if it passes, flips this to "submitted". Submitting never locks the
    # record — editing stays allowed after it. server_default so rows written
    # straight to the table (the Excel loader) come in as drafts without the
    # loader having to set it.
    record_state: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        server_default="draft",
        nullable=False,
        index=True
    )

    # The closed lock. A consignment closes when its status reaches "Arrived
    # at works"; from then on nobody may edit it until an admin reopens it
    # (which clears this flag). This is separate from record_state: a
    # submitted consignment is still editable, a closed one is not.
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True
    )

    # Deleting only sets this flag. The row stays, so an admin or
    # manager can put it back, and so the item lines, payments and
    # history that hang off it are not destroyed along with it.
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

    # A creator is always required. RESTRICT stops a user row being
    # deleted while it still owns consignments; SET NULL here would
    # violate the NOT NULL constraint and make the delete fail anyway.
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )

    #--- links to the user who touched it ---
    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id]
    )

    deleted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[deleted_by_id]
    )

    eta_revisions: Mapped[list["EtaRevisionHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    status_updates: Mapped[list["StatusUpdateHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    change_history: Mapped[list["ConsignmentChangeHistory"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    clearing_agent: Mapped[Optional["ClearingAgent"]] = relationship(
        back_populates="consignments"
    )

    # Two columns point at the same table, so each says which it means
    loading_port: Mapped[Optional["Port"]] = relationship(
        foreign_keys=[loading_port_id],
        back_populates="consignments_loading"
    )

    delivery_port: Mapped[Optional["Port"]] = relationship(
        foreign_keys=[delivery_port_id],
        back_populates="consignments_delivery"
    )

    #--- everything that hangs off a consignment ---
    # delete-orphan means these go when the consignment really goes.
    # Day to day they never do, because deleting only sets a flag.
    items: Mapped[list["ConsignmentItem"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="consignment",
        cascade="all, delete-orphan"
    )

    branch: Mapped[Optional["Branch"]] = relationship(
    back_populates="consignments"
)

    supplier: Mapped[Optional["Supplier"]] = relationship(
        back_populates="consignments"
    )

#--------------------------------
# CONSIGNMENT ITEMS TABLE
#--------------------------------

class ConsignmentItem(Base, TimestampMixin):
    __tablename__ = "consignment_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True
    )

    #--- snapshots taken from the item master ---
    item_code: Mapped[str] = mapped_column(
        String(100),
        nullable=True
    )

    item_name: Mapped[str] = mapped_column(
        String(255),
        nullable=True
    )

    specification: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    hs_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    #--- what was ordered ---
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4),
        nullable=True
    )

    unit_of_measurement: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    batch_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    requisition_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    # Landed cost is typed in by hand, in PKR. Nothing calculates it —
    # duty, freight and agent fees are not tracked in this system.
    elc: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    alc: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    # ELC and ALC are usually entered weeks apart by different people, so each
    # figure records who entered it and when, separately — one updated_by /
    # updated_at pair on the line cannot answer "who entered which".
    elc_updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    elc_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    alc_updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    alc_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Variance = ALC - ELC, stored both as an absolute PKR figure and as a
    # percentage of ELC (recompute_derived). Stored so reports do not recompute.
    variance_absolute: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    variance_percentage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(9, 2),
        nullable=True
    )

    # These four vary line by line, which is why they sit here and not
    # on the consignment. One consignment can carry Store and
    # Engineering items together.
    reference_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    job_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    mo_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(500),
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

    consignment: Mapped["Consignment"] = relationship(
        back_populates="items"
    )

    item: Mapped[Optional["Item"]] = relationship(
        back_populates="consignment_items"
    )

#--------------------------------
# PAYMENTS TABLE
#--------------------------------

class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    retirement_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4),
        nullable=True
    )

    payment_exchange_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6),
        nullable=True
    )

    bank_charges: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="Unpaid",
        nullable=False
    )

    bank_reference: Mapped[Optional[str]] = mapped_column(
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

    consignment: Mapped["Consignment"] = relationship(
        back_populates="payments"
    )


#--------------------------------
# ETA REVISION HISTORY TABLE
#
# The ETA is never simply overwritten. Every change lands here, and the
# "1st ETA was X, 2nd was Y" line in reports is built from these rows.
#--------------------------------

class EtaRevisionHistory(Base, TimestampMixin):
    __tablename__ = "eta_revision_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("consignments.id", ondelete="CASCADE"),
        nullable=False
    )

    # "ETA" or "ETA works". String needs an explicit length for MySQL.
    eta_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )

    previous_eta: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    new_eta: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )

    cause_of_revision: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    consignment: Mapped["Consignment"] = relationship(
        back_populates="eta_revisions"
    )

    user: Mapped[Optional["User"]] = relationship()


#--------------------------------
# STATUS UPDATE HISTORY TABLE
#
# effective_date is the day the stage actually changed, which is often
# not the day somebody got round to entering it. Clearance timing
# counts from the effective date of the "Arrived at port" row.
#--------------------------------

class StatusUpdateHistory(Base, TimestampMixin):
    __tablename__ = "status_update_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("consignments.id", ondelete="CASCADE"),
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
        nullable=True,
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

    consignment: Mapped["Consignment"] = relationship(
        back_populates="status_updates"
    )

    user: Mapped[Optional["User"]] = relationship()


#--------------------------------
# CONSIGNMENT CHANGE HISTORY TABLE
#
# One row per update or delete, holding the values as they were before
# the change. That is what makes reverting possible: putting a
# consignment back means writing previous_values onto it again.
#
# Only the fields that actually changed are stored, not the whole
# record, so it is obvious from one row what somebody touched.
#
# The activity log records THAT something happened. This records WHAT
# it was before, so it can be undone.
#--------------------------------

class ConsignmentChangeHistory(Base, TimestampMixin):
    __tablename__ = "consignment_change_history"
    __table_args__ = (
        Index("ix_change_history_consignment", "consignment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    consignment_id: Mapped[int] = mapped_column(
        ForeignKey("consignments.id", ondelete="CASCADE"),
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

    # True when this row was itself created by a revert. Kept so the
    # history reads honestly rather than looking like a normal edit.
    is_revert: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    consignment: Mapped["Consignment"] = relationship(
        back_populates="change_history"
    )

    changed_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[changed_by_id]
    )

    reverted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[reverted_by_id]
    )