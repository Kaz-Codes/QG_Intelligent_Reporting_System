from datetime import datetime
from typing import Optional

from app.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Integer, Table, Column, ForeignKey, Boolean, DateTime, text,
)
from app.models_mixins import TimestampMixin

#-----------------------------------------------------
# ACCOUNTS + PERMISSIONS
#
# There are no roles. A user is either an admin (is_admin, which passes every
# authorization check) or a normal account holding an explicit set of
# permissions. Users and permissions are many-to-many: a user has many
# permissions, and a permission is held by many users.
#
# The permission NAMES are the catalogue in app/accounts/permissions.py; they
# are seeded into this table at startup.
#-----------------------------------------------------

#--------------------------------
# USER <-> PERMISSION BRIDGE (MANY-MANY)
#--------------------------------

user_permission = Table(
    "user_permissions",
    Base.metadata,
    Column(
        "user_id",
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False
    ),
    Column(
        "permission_id",
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False
    ),
)


#--------------------------------
# PERMISSIONS TABLE
#--------------------------------

class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    users: Mapped[list["User"]] = relationship(
        secondary=user_permission,
        back_populates="permissions"
    )


#--------------------------------
# USERS TABLE
#--------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    username: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    # An admin passes every authorization check, including account management.
    # The account-creation checkbox on the front end sets this flag. server_
    # default so rows written outside the ORM (should any be) come in as
    # non-admin rather than NULL.
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )

    #--- notifications ---
    # How much this account wants to receive. NOT a role — authorization is
    # is_admin plus the permission catalogue, and this changes none of it.
    # It is a volume control: see app/notifications/routing.py, which owns how
    # this compares against an event's own tier. NotificationTier value.
    #
    # server_default as well as default: these columns are being added to a
    # table that already has rows, so the database needs a value to backfill
    # them with — a Python-side default alone would leave the ALTER unable to
    # make the column NOT NULL.
    notification_tier: Mapped[str] = mapped_column(
        String(20),
        default="operational",
        server_default="operational",
        nullable=False
    )

    # E.164 ONLY — a leading '+', country code, no spaces, no dashes, no
    # brackets: +923001234567. Not a display format. WhatsApp and every other
    # provider reject anything else, and a column holding "0300-1234567" for
    # some rows and "+92 300 1234567" for others cannot be normalised later
    # without guessing at the country.
    phone_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True
    )

    # Consent to be messaged on WhatsApp, and WHEN it was given. Meta requires
    # a record of opt-in, and a bare boolean cannot evidence one — "they
    # agreed" without a date is not something you can produce on request. The
    # two move together: never set the flag without the timestamp.
    whatsapp_opted_in: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False
    )

    whatsapp_opted_in_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=user_permission,
        back_populates="users"
    )
