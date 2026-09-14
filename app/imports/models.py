from datetime import date, datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from app.database import Base
from app.models_mixins import TimestampMixin

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, text,
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
# CONSIGNMENT BATCH GROUPS TABLE
#
# The LC / order that one or more consignments (batches) are shipped against.
#
# A consignment used to BE the order: one row held the commercial terms, the
# finance and the goods together. Splitting one order across several shipments
# needs the commercial half to live once, above the shipments, or the same LC's
# supplier and exchange rate exist in as many copies as there are batches and
# nothing says which copy is authoritative.
#
# THE GROUP HAS NO NUMBER COLUMN. The number an operator sees is the FOUNDING
# consignment's id, which is why founding_consignment_id is here and a `number`
# is not: a stored number would be a second copy of an identity that already
# exists, and two copies drift. Every consignment migrated by revision A founds
# its own group, so every existing number displays exactly as it does today.
#
# A dedicated table, rather than a self-referential FK from batch to founding
# batch: deleting the founding batch must not orphan the group, and the rules
# say every batch is equal and any of them may be deleted.
#--------------------------------

class ConsignmentBatchGroup(Base, TimestampMixin):
    __tablename__ = "consignment_batch_groups"

    id: Mapped[int] = mapped_column(primary_key=True)

    # The batch whose id IS this group's displayed number. Not "batch 1" in any
    # privileged sense - it may be deleted like any other - only the row whose
    # id the number was taken from.
    # DEFERRABLE, and so is Consignment.batch_group_id. The two tables
    # reference each other and BOTH columns are NOT NULL, so with the checks
    # done per statement there is no order in which a new order and its first
    # batch can be inserted at all: the group needs a consignment that does not
    # exist yet, and the consignment needs a group that does not exist yet.
    # Deferring to COMMIT still enforces both - a transaction leaving either
    # side dangling fails - it only lets the pair be inserted together.
    founding_consignment_id: Mapped[int] = mapped_column(
        # use_alter tells create_all to add THIS constraint by ALTER once both
        # tables exist. Without it SQLAlchemy cannot sort the two tables (they
        # depend on each other), warns that it is ignoring the cycle, and says
        # the warning may become an error in a later release. It affects only
        # how create_all emits DDL on a brand-new database; Alembic is the
        # source of truth for schema changes either way.
        ForeignKey("consignments.id", ondelete="RESTRICT",
                   deferrable=True, initially="DEFERRED", use_alter=True),
        nullable=False,
        index=True
    )

    # How many batches this group has EVER held: incremented on creation, never
    # decremented. It exists so the display rule - a suffix only once a group
    # has held two or more - is a column read rather than a window function
    # over soft-deleted siblings on every list query.
    #
    # server_default because the loaders insert through raw psycopg2, where a
    # Python-side default never runs.
    batches_ever: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False
    )

    #--- shared across every batch in the group ---
    # These are facts about the ORDER, not about a shipment. They stay on
    # `consignments` as well until revision B drops them there; the group is the
    # only one of the two copies that is read.
    supplier_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True
    )

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

    incoterm: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True
    )

    payment_instrument: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    instrument_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    #--- entered once, on the first batch: Step 2 Finance ---
    # The rate is booked against the ORDER, so every batch of one LC converts at
    # the same rate. Held per batch instead, two shipments of one order could
    # report different PKR values for the same money.
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

    # The header-level branch, and the successor to BOTH Consignment.works (free
    # text) and Consignment.branch_id (the FK the sheet's "Works" column filled).
    # Works and Branch were always the same thing to the business; this is the
    # one column that says so. Items carry their own branch_id for the per-item
    # variation.
    works_branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True
    )

    #--- Step 4 Payments, LC-level ---
    # Insurance is taken out on the order, not on each shipment. NOTHING WRITES
    # THIS YET: the payment move is a later phase, and the column is here
    # because section 4.1 of the design puts it here.
    insurance_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2),
        nullable=True
    )

    #--- state ---
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

    # Nullable, unlike Consignment.created_by_id, because the back-fill creates
    # a group for every consignment that already exists and the person who
    # founded the ORDER is not a fact the old rows record. It is the
    # consignment's creator where one is known and NULL is never guessed.
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True
    )

    #--- relationships ---
    # `batches` needs an explicit foreign_keys: consignments and this table
    # reference each other in both directions (batch_group_id one way,
    # founding_consignment_id the other), so the join is ambiguous without it.
    batches: Mapped[list["Consignment"]] = relationship(
        back_populates="batch_group",
        foreign_keys="Consignment.batch_group_id"
    )

    founding_consignment: Mapped["Consignment"] = relationship(
        foreign_keys=[founding_consignment_id]
    )

    order_items: Mapped[list["ConsignmentOrderItem"]] = relationship(
        back_populates="batch_group",
        cascade="all, delete-orphan"
    )

    supplier: Mapped[Optional["Supplier"]] = relationship(
        back_populates="consignment_groups"
    )

    works_branch: Mapped[Optional["Branch"]] = relationship(
        back_populates="consignment_groups"
    )

    created_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[created_by_id]
    )

    deleted_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[deleted_by_id]
    )


#--------------------------------
# CONSIGNMENT ORDER ITEMS TABLE
#
# One row per item ON THE ORDER - what was bought - against which each batch's
# ConsignmentItem rows record what that shipment actually carried.
#
# The rule that decides which of the two tables a field belongs to: a fact about
# what was ORDERED lives here; a fact about what happened to a PARTICULAR
# SHIPMENT lives on consignment_items. So the item's identity, the ordered
# quantity, the price and the demand dates are here, while the arrival date, the
# landed cost and the physical weights stay on the line - landed cost is
# incurred per arrival, and two batches of one item legitimately land at
# different costs.
#
# NOTHING WRITES TO THIS TABLE YET. Revision A creates it and back-fills one row
# per existing consignment line; allocation and batch creation are a later
# phase.
#--------------------------------

class ConsignmentOrderItem(Base, TimestampMixin):
    __tablename__ = "consignment_order_items"

    __table_args__ = (
        # THE BACKSTOP, NOT THE ENFORCEMENT. The real rule is that the SUM of a
        # group's batch lines may not exceed what was ordered, and no CHECK can
        # express that: the quantities being summed live on rows of a different
        # table, under different consignments. The server holds a row lock on
        # this row and checks the sum before writing - that is the enforcement.
        #
        # `allocated_quantity` is that sum, denormalised onto the parent row
        # where a CHECK *can* see it. It catches any path that skips the server
        # check - including the loaders, which bypass the ORM entirely and are
        # exactly the kind of code that forgets.
        CheckConstraint(
            "allocated_quantity <= ordered_quantity",
            name="ck_allocation_within_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    batch_group_id: Mapped[int] = mapped_column(
        ForeignKey("consignment_batch_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    #--- identity, moved up from the line ---
    item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True
    )

    item_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    item_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    placeholder_name: Mapped[Optional[str]] = mapped_column(
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

    #--- quantity ---
    # What was bought. Each batch line's own `quantity` is an allocation against
    # this, and the sum of those allocations is mirrored into
    # allocated_quantity below.
    ordered_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=False
    )

    allocated_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        default=0,
        server_default=text("0"),
        nullable=False
    )

    unit_of_measurement: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    #--- money ---
    # Which of the two prices below applies. See enums.PriceBasis: both formulas
    # are real and the choice is per line, so neither price column ever has to
    # carry the other's meaning.
    price_basis: Mapped[str] = mapped_column(
        String(20),
        default="quantity",
        server_default="quantity",
        nullable=False
    )

    # Price for one `unit_of_measurement`, in the group's currency. Widened from
    # the line's Numeric(14,4) to the Numeric(18,4) the conventions ask for for
    # a unit price - a widening, so every copied value survives it exactly.
    unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4),
        nullable=True
    )

    # Price per KILOGRAM, used only when price_basis is 'weight'.
    weight_unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 4),
        nullable=True
    )

    # Kilograms PER UNIT - deliberately not the line's total. A separate column
    # from ConsignmentItem.net_weight, which is documented as the total for the
    # whole quantity and keeps that meaning; multiplying quantity by a total
    # would count the quantity twice.
    unit_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    #--- the demand this line came from ---
    # Per item, because one order can carry lines demanded by different branches
    # on different dates.
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True
    )

    requisition_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    required_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True
    )

    requisition_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

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
        server_default=text("false"),
        nullable=False,
        index=True
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    batch_group: Mapped["ConsignmentBatchGroup"] = relationship(
        back_populates="order_items"
    )

    item: Mapped[Optional["Item"]] = relationship(
        back_populates="consignment_order_items"
    )

    branch: Mapped[Optional["Branch"]] = relationship()

    lines: Mapped[list["ConsignmentItem"]] = relationship(
        back_populates="order_item"
    )


#--------------------------------
# CONSIGNMENTS TABLE
#--------------------------------

class Consignment(Base, TimestampMixin):
    __tablename__ = "consignments"

    __table_args__ = (
        # A sequence number is unique WITHIN its group and is never reused, so
        # 177-2 identifies one shipment for ever. Deleting a batch leaves a gap
        # rather than renumbering its siblings: renumbering would make an old
        # 177-3 become 177-2, and a number already on an invoice would then
        # resolve to a different shipment with both parties believing they
        # agree.
        Index(
            "uq_consignments_group_sequence",
            "batch_group_id", "batch_sequence",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    #--- which order this consignment is a batch of ---
    # NOT NULL: revision A back-fills a group of one for every consignment that
    # already exists, so there is no window in which a consignment has no order
    # above it and no code that has to handle the NULL case.
    # No index=True: uq_consignments_group_sequence in __table_args__ above is a
    # unique index LEADING with this column, so it already serves lookups by
    # group and the foreign key check. A second index on the same column would
    # cost a write on every save and answer nothing the first cannot.
    batch_group_id: Mapped[int] = mapped_column(
        ForeignKey("consignment_batch_groups.id", ondelete="RESTRICT",
                   deferrable=True, initially="DEFERRED"),
        nullable=False
    )

    # This batch's position in its group. Assigned at creation, NEVER reused and
    # never changed - see the unique index above for why. server_default
    # because the loaders insert through raw psycopg2.
    batch_sequence: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False
    )

    #-----------------------------------------------------------------
    # FOURTEEN ATTRIBUTES USED TO BE HERE. THE COLUMNS STILL EXIST.
    #
    #   to the ORDER (consignment_batch_groups) - facts about what was agreed,
    #   identical on every batch of one LC:
    #       supplier_id  origin  currency  consignment_type  incoterm
    #       payment_instrument  instrument_number
    #       exchange_rate  rate_booked_on  rate_source
    #       branch_id -> works_branch_id   (RENAMED: works and branch were
    #                    always the same thing to the business, and the group
    #                    is where the header-level branch now lives)
    #
    #   to the ORDER LINE (consignment_order_items) - facts about the demand,
    #   which can differ item by item within one order:
    #       requisition_date  required_date
    #
    #   RETIRED, with no successor anywhere:
    #       works  (free text; works_branch_id above replaces it)
    #
    # THE COLUMNS ARE DELIBERATELY LEFT IN THE DATABASE. Revision B drops them,
    # a release later, once batching has actually run. Removing the ATTRIBUTES
    # while leaving the columns is the control section 4.7 is built on:
    # SQLAlchemy cannot write a column it does not know about, so no ORM path
    # can keep the orphaned copy alive.
    #
    # THAT CONTROL COVERS LESS THAN IT APPEARS TO, and section 4.7 now lists
    # five ways round it - two of which were found by running the code, not by
    # reading it. Anything that writes ONE copy while both exist is suspect.
    #
    # `po_date` stays for now (section 4.8): it is duplicated nowhere, so
    # leaving it mapped creates no divergence risk, and retiring it has a
    # front-end consequence that does not belong in this change.
    #-----------------------------------------------------------------

    clearing_agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clearing_agents.id", ondelete="SET NULL"),
        nullable=True
    )

    po_date: Mapped[Optional[date]] = mapped_column(
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
    # payment_instrument, instrument_number, exchange_rate, rate_booked_on and
    # rate_source are on the ORDER now - see the block above. The rate is booked
    # against the LC, so every batch of one order converts at the same rate;
    # held per batch, two shipments of one order could report different PKR
    # values for the same money.
    #
    # `opening_or_retirement_date` stays per batch: it is the date THIS
    # shipment's instrument was opened or retired, not a term of the order.
    opening_or_retirement_date: Mapped[Optional[date]] = mapped_column(
        Date,
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
        String(2000),
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

    #--- cross-module hand-off ---
    # When this consignment was handed to Logistics (shipping + clearing) and
    # to Trucking (inland movement). NULL means "not sent". They are the
    # record of INTENT: nothing reaches either module until someone sends it,
    # which is why the trucking inbox keys off sent_to_trucking_at rather than
    # inferring from the incoterm (FOB only decides whether Send is OFFERED).
    #
    # Timestamps rather than booleans because "when was this handed over" is
    # the question people actually ask, and a bool answers strictly less.
    # Set only by the dedicated send routes — never by a normal update.
    sent_to_logistics_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    sent_to_trucking_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    # "A user has marked this record finished. NOTHING VERIFIES THAT CLAIM."
    #
    # It used to mean "this record has passed the full rule set", which is a
    # stronger statement; imports has no rule set any more. It now drives
    # exactly one thing — the `drafts_only` list filter — and is otherwise
    # informational and a column in the export.
    #
    # It is NOT half of the closed test. Closing is the status alone (see
    # helpers.is_closed), so a submitted consignment and a draft at the same
    # status are equally closed or equally open.
    #
    # server_default so rows written straight to the table (the Excel loader)
    # come in as drafts without the loader having to set it.
    record_state: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        server_default="draft",
        nullable=False,
        index=True
    )

    # The closed lock. A consignment closes when its status reaches "Arrived
    # at works"; from then on nobody may edit it until an admin reopens it
    # (which clears this flag). Independent of record_state entirely.
    #
    # WRITTEN BY THE UPDATE ROUTE, on the transition into that status, and
    # nowhere else in the app. It was previously written by /submit and nowhere
    # else, which is why CLAUDE.md's claim that the update route set it was
    # wrong and why all 142 locked rows in production were locked by the Excel
    # loader rather than by anybody using the system.
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

    # `branch` and `supplier` are GONE from the batch. They had no columns left
    # to join on once branch_id and supplier_id moved to the order, so they die
    # with them rather than being repointed: a relationship declared here would
    # say the batch owns a supplier, and it does not.
    #
    # Read them through `consignment.batch_group.supplier` /
    # `.works_branch`, or — better at a call site — through
    # app/imports/order_view.py, which hides the navigation and keeps the
    # OWNERSHIP visible in the name (`order_supplier_name`, not `.supplier`).

    # foreign_keys is explicit because consignments and consignment_batch_groups
    # point at each other: this column one way, founding_consignment_id the
    # other. Without it the join is ambiguous.
    batch_group: Mapped["ConsignmentBatchGroup"] = relationship(
        back_populates="batches",
        foreign_keys=[batch_group_id]
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

    # THE ORDER LINE THIS SHIPMENT LINE IS AN ALLOCATION AGAINST.
    #
    # `quantity` below becomes the quantity allocated to THIS batch; what was
    # ordered lives once, on the order item. NOT NULL: revision A back-fills one
    # order item per existing line, so no line is left without one.
    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("consignment_order_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    #-----------------------------------------------------------------
    # THIRTEEN ATTRIBUTES USED TO BE HERE. THE COLUMNS STILL EXIST.
    #
    # All thirteen moved to the ORDER LINE (consignment_order_items), because
    # they describe WHAT WAS BOUGHT rather than what this shipment carried:
    #
    #   item_id  item_code  item_name  placeholder_name  specification  hs_code
    #   unit_price  unit_of_measurement
    #   requisition_type  reference_number  job_number  mo_number  description
    #
    # The rule that decides which table a field belongs to (section 3.7): a fact
    # about what was ORDERED lives on the order line; a fact about what happened
    # to a PARTICULAR SHIPMENT stays here. So the identity, the price and the
    # requisition details went up, while `quantity` (now the ALLOCATED quantity),
    # the arrival date, the landed cost and the physical weights stayed - landed
    # cost is incurred per arrival, and two batches of one item legitimately land
    # at different costs.
    #
    # Revision B drops the columns. Reach them through `line.order_item`.
    #-----------------------------------------------------------------

    #--- what THIS shipment carried ---
    # The ALLOCATED quantity. What was ordered lives once, on the order line;
    # this is how much of it came in this batch.
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    # THE LINE'S OWN ARRIVAL DATE.
    #
    # A consignment groups every sheet row sharing a payment reference, and
    # those rows do NOT all arrive together: 19 of 175 consignments carry lines
    # with different ETAs, one of them spanning seven distinct dates. The header
    # keeps a single `eta_works` (the first line's), so dating a whole
    # consignment by it attributes money to a month it did not land in —
    # ref 65704 reported Rs 10.64m in August when Rs 1.66m of it arrived on
    # 27 July.
    #
    # Nullable: the sheet does not always give a per-line date, and a line
    # without one falls back to its consignment's.
    eta_works: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    batch_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )

    #--- weight & dimensions ---
    # Optional at draft; the imports team is expected to fill these before an
    # FOB consignment is handed to trucking, since the truck load-out and
    # freight rate depend on them. net_weight is the line's total for its
    # whole quantity (not a per-unit figure) — mirrors LogisticsItem's
    # gross_weight convention (Numeric(14,3), kg).
    net_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    gross_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3),
        nullable=True
    )

    # cm.
    length: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    width: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    height: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
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

    # requisition_type, reference_number, job_number, mo_number and
    # description are on the ORDER LINE now. They vary line by line - one order
    # can carry Store and Engineering items together - but they describe the
    # DEMAND the line came from, not the shipment, so they went up with the rest
    # of the order-level identity rather than staying beside the arrival.

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

    # `item` is GONE from the shipment line - item_id went to the order line,
    # so there is nothing here to join on. Reach the master through
    # `line.order_item.item`.

    order_item: Mapped["ConsignmentOrderItem"] = relationship(
        back_populates="lines"
    )

    # WHO ENTERED EACH LANDED-COST FIGURE. The FK columns above have existed
    # since rule 11; these are the relationships that let anything actually
    # PRINT the name, added for the export (build-order step 2) - a sheet
    # showing an ELC without who entered it is the wrong half of a rule that
    # exists to make somebody accountable for the number.
    #
    # `foreign_keys` is required, not decorative: there are TWO FKs to `users`
    # on this table and SQLAlchemy cannot choose between them. Without it,
    # mapper configuration fails with an ambiguous-join error - which
    # `configure_mappers()` catches and a bare import does not.
    #
    # No DDL: both columns are already in the database.
    elc_updated_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[elc_updated_by_id]
    )

    alc_updated_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[alc_updated_by_id]
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