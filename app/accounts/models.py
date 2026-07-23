from app.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Table, Column, ForeignKey, Boolean
from app.models_mixins import TimestampMixin

#-----------------------------------------------------
# BRIDGE TABLE BTW ROLES AND PERMISSIONS (MANY-MANY)
#-----------------------------------------------------

role_permission = Table(
    "roles_permissions",
    Base.metadata,
    Column(
        "role_id",
        ForeignKey("roles.id"),
        primary_key=True,
        nullable=False
    ),
    Column(
        "permission_id",
        ForeignKey("permissions.id"),
        primary_key=True,
        nullable=False
    ),
)

#--------------------------------
# ROLES AND PERMISSION TABLES
#--------------------------------

class Role(Base):
    __tablename__ = "roles"
    id : Mapped[int] = mapped_column(
        Integer,
        primary_key = True
    )
    name : Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    permissions : Mapped[list["Permission"]] = relationship(
        secondary = role_permission,
        back_populates = "roles"
    )
    users : Mapped[list["User"]] = relationship(
            back_populates = "role"
    )

class Permission(Base):
    __tablename__ = "permissions"
    id : Mapped[int] = mapped_column(
        Integer,
        primary_key = True
    )
    name : Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    roles : Mapped[list["Role"]] = relationship(
            secondary = role_permission,
            back_populates = "permissions"
    )

#--------------------------------
# USERS TABLE
#--------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(
        Integer,
        primary_key = True
    )

    username : Mapped[str] = mapped_column(
        String(255),
        unique = True,
        nullable = False
    )

    password : Mapped[str] = mapped_column(
        String(255),
        nullable = False
    )

    role_id : Mapped[int] = mapped_column(
        ForeignKey("roles.id"),
        nullable = False
    )

    role : Mapped["Role"] = relationship(
        back_populates = "users"
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = False,
        nullable = False,
        index = True
    )