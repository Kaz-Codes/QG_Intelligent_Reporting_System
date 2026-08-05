from app.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Table, Column, ForeignKey, Boolean, text
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

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=user_permission,
        back_populates="users"
    )
