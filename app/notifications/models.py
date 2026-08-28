from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, DateTime, ForeignKey, Index, Integer, String, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import NotificationChannel, NotificationDeliveryStatus
from app.models_mixins import TimestampMixin

#-----------------------------------------------------
# THE NOTIFICATION TABLES
#
#     NotificationEvent      something happened, once
#       |
#       +-- NotificationDelivery   one row per recipient per channel
#
#     NotificationState      what a threshold was last seen to be
#
# THESE SIT BESIDE THE OPERATIONAL DATA, NOT INSIDE IT. Nothing in imports,
# logistics, trucking or stores points at these tables, and nothing here is
# required for a consignment to exist or to save. The dependency runs one way
# only — a notification may name a consignment, a consignment never knows it
# was notified about. That is what lets emission fail without taking a
# business transaction down with it.
#
# THIS IS NOT THE ACTIVITY LOG. app/logs/ already records every data-changing
# request, generically, for audit. These rows are the opposite: a small,
# curated set of business events somebody is expected to ACT on. Nothing here
# is derived from activity_logs.
#-----------------------------------------------------


#--------------------------------
# NOTIFICATION EVENTS
#
# One row per real-world event, however many people end up receiving it. The
# rendered title/body are stored rather than re-rendered on read: the message
# has to keep saying what it said at the time, even after the underlying
# consignment moves on.
#--------------------------------

class NotificationEvent(Base, TimestampMixin):
    __tablename__ = "notification_events"
    __table_args__ = (
        # The panel reads newest-first, and the retention job deletes
        # oldest-first; both want this.
        Index("ix_notification_events_created_at", "created_at"),

        # DEDUPE. Partial and UNIQUE: the same real-world event emitted twice
        # must not become two notifications. emit() inserts optimistically and
        # treats the resulting IntegrityError as a no-op success, rather than
        # checking first — a check-then-insert races against a concurrent
        # emit and lets both through.
        #
        # Partial because most events carry no key. Postgres already allows
        # repeated NULLs in a unique index, so the predicate is not what makes
        # this correct — it just keeps the index to the rows it polices.
        Index(
            "uq_notification_events_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),

        # THE FAN-OUT QUEUE. Partial on purpose: the worker only ever asks for
        # unprocessed rows, and those are a handful at any moment, so this
        # index stays the size of the backlog rather than the size of the
        # table — however many million events accumulate behind it.
        Index(
            "ix_notification_events_fanout_queue",
            "id",
            postgresql_where=text("fanned_out_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The catalogue key, e.g. "imports.eta_slipped_major". Indexed because
    # both the panel filter and any per-type retention rule read by it.
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    # NotificationSeverity / NotificationTier / NotificationModule. Copied
    # from the catalogue at emit time rather than looked up on read, so an
    # event keeps the classification it was raised under even if the
    # catalogue is later re-tuned.
    severity: Mapped[str] = mapped_column(String(20), nullable=False)

    tier: Mapped[str] = mapped_column(String(20), nullable=False)

    module: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True
    )

    #--- the rendered message ---
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    body: Mapped[str] = mapped_column(String(2000), nullable=False)

    #--- what it is about ---
    # DELIBERATELY NOT A FOREIGN KEY. entity_type/entity_id are polymorphic —
    # a consignment, a logistics order, a trucking job or a stock line — so
    # there is no single table to point at. More importantly, a real FK here
    # would make an operational row undeletable while a notification about it
    # survived, which is exactly the coupling these tables exist to avoid.
    # Click-through resolves it; nothing enforces it.
    entity_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # The branch the event concerns. Indexed because branch is the natural way
    # to narrow a feed, and because rank is per branch — see the catalogue.
    branch: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    # The template variables the title and body were rendered from. Kept so a
    # message can be re-rendered after a template fix, and so a wrong-looking
    # notification can be explained without guessing at its inputs.
    payload: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False
    )

    # Built per event type from whatever makes that event unique — see
    # catalogue.py. NULL means "this event type does not dedupe".
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # WHEN THE WORKER FINISHED ROUTING THIS EVENT. NULL means "still queued".
    #
    # This is the work queue, and it exists because the obvious alternative
    # does not work. Polling for "events that have no delivery rows yet" looks
    # equivalent and is not: an event can legitimately reach NOBODY — no
    # active user holds the permission, or everyone is tiered above it — and
    # such an event never gets a delivery row, so it stays a candidate for
    # ever. Once a hundred of those accumulate they fill every batch, ordered
    # by id, and fan-out stops making progress entirely while looking busy.
    #
    # Marking the EVENT as processed separates "we routed this" from "somebody
    # received it", which are genuinely different facts.
    fanned_out_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan"
    )


#--------------------------------
# NOTIFICATION DELIVERIES
#
# The fan-out: one row per recipient per channel. Read state lives here and
# not on the event, because two people reading the same event are two
# different facts.
#--------------------------------

class NotificationDelivery(Base, TimestampMixin):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        # THE ONLY TWO HOT READS, both served by this one index: the unread
        # badge (user + read_at IS NULL) and the panel (that, newest first).
        Index(
            "ix_notification_deliveries_user_read_created",
            "user_id", "read_at", "created_at",
        ),
        # Not redundant with the composite above: the retention job deletes by
        # age across all users, which cannot use a user_id-leading index.
        Index("ix_notification_deliveries_created_at", "created_at"),

        # THE GROUPING LOOKUP: "how many deliveries has each of these users
        # had in the last hour", asked once per event by the fan-out worker
        # (routing.assign_group_keys) and narrowed to a module and severity by
        # a join to notification_events.
        #
        # (user_id, created_at) and NOT the composite above: that one is
        # (user_id, read_at, created_at), and read_at sitting in the middle
        # makes it useless for a plain time-range scan per user — Postgres
        # cannot skip a middle column to range-scan the third.
        #
        # NOT partial on group_key IS NOT NULL, which was the first instinct
        # and is exactly backwards: the count has to include the UNGROUPED
        # deliveries, because they are what pushes a user over the threshold
        # in the first place. A partial index there would only ever see the
        # rows that had already been grouped.
        Index("ix_notification_deliveries_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # CASCADE both ways on purpose: a delivery is meaningless without its
    # event, and a departed user's notifications are not worth keeping. Note
    # this is the notifications module depending on accounts, never the
    # reverse.
    event_id: Mapped[int] = mapped_column(
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    channel: Mapped[str] = mapped_column(
        String(20),
        default=NotificationChannel.IN_APP.value,
        server_default=NotificationChannel.IN_APP.value,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=NotificationDeliveryStatus.PENDING.value,
        server_default=NotificationDeliveryStatus.PENDING.value,
        nullable=False
    )

    # The provider's own message id — WhatsApp/email later. Kept so a delivery
    # can be reconciled against the provider's status callbacks.
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # NULL means unread. A nullable timestamp rather than a bool because "when
    # did they see this" is the question actually asked of it, and a bool
    # answers strictly less — the same reasoning as the imports hand-off
    # timestamps.
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    #--- delivery grouping ---
    #
    # NULL for the great majority of deliveries, which stand on their own.
    # Set by the fan-out worker when this recipient is already over the
    # threshold for (user, module, severity) within the hour, so the panel can
    # collapse the run into one expandable entry — "12 consignments updated in
    # Imports" — instead of burying everything else under it.
    #
    # THE GROUPING IS A PRESENTATION DECISION RECORDED ON THE ROW, NOT A
    # DIFFERENT KIND OF ROW. Every grouped delivery is still a full delivery:
    # its own read state, its own event, its own click-through. That is why
    # this is a nullable column rather than a separate "digest" table — a
    # digest row would have to duplicate what it summarises, and reading one
    # would not mark the underlying notifications read.
    #
    # Assigned at FAN-OUT rather than at emit, because whether something needs
    # grouping is a fact about one recipient's hour, not about the event: the
    # same consignment update is the eleventh thing for a clerk watching that
    # module and the first for anybody else.
    group_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    event: Mapped["NotificationEvent"] = relationship(back_populates="deliveries")


#--------------------------------
# NOTIFICATION STATE
#
# THRESHOLDS FIRE ON TRANSITION, NOT ON CONDITION. "Below reorder level" is
# true continuously once it starts being true, so an emitter that fires on
# the CONDITION re-notifies every single scan until somebody restocks. This
# table remembers what the threshold was last seen to be, so an event is
# raised only when the answer CHANGES.
#
# One row per watched thing, keyed by a string the scanner builds — e.g.
# "reorder:ITM001:LHR". Per BRANCH, never folded across branches: an item can
# be below its reorder level at one branch and fine at another, and so can
# its ABC rank.
#--------------------------------

class NotificationState(Base, TimestampMixin):
    __tablename__ = "notification_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    state_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    # e.g. "below" / "above". Free-form on purpose: each scanner defines the
    # states its own threshold can be in.
    state_value: Mapped[str] = mapped_column(String(50), nullable=False)

    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # SET NULL, not CASCADE: if the event this state last raised is purged by
    # retention, the STATE must survive — losing it would make the threshold
    # look untracked and re-fire on the next scan, which is the exact
    # behaviour this table exists to prevent.
    last_event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notification_events.id", ondelete="SET NULL"),
        nullable=True
    )
