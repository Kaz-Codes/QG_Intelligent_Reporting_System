from typing import Optional, TYPE_CHECKING

from app.database import Base
from app.models_mixins import TimestampMixin

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.loading.schemas.stores_schemas import Stock, Issuance, PurchasesData, StoreRequisition

# Only used inside quoted "Mapped[...]" annotations, which SQLAlchemy resolves
# from its class registry. A real import here would make masters.models and
# imports.models import each other in a circle, so it is for the type checker
# only.
if TYPE_CHECKING:
    from app.imports.models import Consignment, ConsignmentItem


#-----------------------------------------------------
# MASTER TABLES
#
# The lists that fill the dropdowns. They live here rather than being
# typed as free text, because people spell things three ways and then
# supplier-wise reporting stops working.
#
# is_active    turns a row off without removing it. Consignments
#              already pointing at it keep working.
#
# is_verified  a row created in the middle of data entry starts False
#              and waits in the Masters review queue. Rows created
#              through the Masters screen are True from the start.
#-----------------------------------------------------


#--------------------------------
# SUPPLIERS TABLE
#--------------------------------

class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id : Mapped[int] = mapped_column(primary_key = True)

    name : Mapped[str] = mapped_column(
        String(255),
        unique = True,
        nullable = False
    )

    country : Mapped[str] = mapped_column(
        String(255),
        nullable = False
    )

    city : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    contact_name : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    phone : Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable = True
    )

    email : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    # Copied onto a consignment as its starting value, then editable there
    default_currency : Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable = True
    )

    default_payment_terms : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    is_verified : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    consignments : Mapped[list["Consignment"]] = relationship(
        back_populates = "supplier"
    )


#--------------------------------
# BRANCHES TABLE
#--------------------------------

class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    id : Mapped[int] = mapped_column(primary_key = True)

    name : Mapped[str] = mapped_column(
        String(255),
        unique = True,
        nullable = False
    )

    code : Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable = True
    )

    city : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    address : Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable = True
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    # Branches are never created inline, so this is always True.
    # Kept so every master table has the same shape.
    is_verified : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    consignments : Mapped[list["Consignment"]] = relationship(
        back_populates = "branch"
    )


#--------------------------------
# WORKS TABLE
#--------------------------------

class Works(Base, TimestampMixin):
    __tablename__ = "works"

    id : Mapped[int] = mapped_column(primary_key = True)

    name : Mapped[str] = mapped_column(
        String(255),
        unique = True,
        nullable = False
    )

    code : Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable = True
    )

    ntn_strn : Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable = True
    )

    note : Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable = True
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    is_verified : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    # Works is no longer a foreign key on the consignment (it is typed in by
    # hand there), so this table has no consignment back-reference.


#--------------------------------
# PORTS TABLE
#
# Loading and delivery ports share one table. used_as decides which
# dropdown a port appears in on the shipping step.
#--------------------------------

class Port(Base, TimestampMixin):
    __tablename__ = "ports"

    id : Mapped[int] = mapped_column(primary_key = True)

    name : Mapped[str] = mapped_column(
        String(255),
        unique = True,
        nullable = False
    )

    country : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    port_type : Mapped[str] = mapped_column(
        String(20),
        default = "Sea",
        nullable = False
    )

    un_locode : Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable = True
    )

    used_as : Mapped[str] = mapped_column(
        String(20),
        default = "Both",
        nullable = False
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    is_verified : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    # A consignment points at this table twice, so each side has to say
    # which column it means.
    consignments_loading : Mapped[list["Consignment"]] = relationship(
        foreign_keys = "Consignment.loading_port_id",
        back_populates = "loading_port"
    )

    consignments_delivery : Mapped[list["Consignment"]] = relationship(
        foreign_keys = "Consignment.delivery_port_id",
        back_populates = "delivery_port"
    )

    clearing_agents : Mapped[list["ClearingAgent"]] = relationship(
        back_populates = "primary_port"
    )


#--------------------------------
# CLEARING AGENTS TABLE
#--------------------------------

class ClearingAgent(Base, TimestampMixin):
    __tablename__ = "clearing_agents"

    id : Mapped[int] = mapped_column(primary_key = True)

    name : Mapped[str] = mapped_column(
        String(255),
        unique = True,
        nullable = False
    )

    licence_no : Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable = True
    )

    contact_name : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    phone : Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable = True
    )

    primary_port_id : Mapped[Optional[int]] = mapped_column(
        ForeignKey("ports.id", ondelete = "SET NULL"),
        nullable = True
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    is_verified : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    primary_port : Mapped[Optional["Port"]] = relationship(
        back_populates = "clearing_agents"
    )

    consignments : Mapped[list["Consignment"]] = relationship(
        back_populates = "clearing_agent"
    )


#--------------------------------
# ITEMS TABLE
#
# The catalogue. When somebody picks an item on step 1, the code,
# specification and unit are copied onto the consignment line as a
# starting point and can then be changed on that line.
#--------------------------------

class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id : Mapped[int] = mapped_column(primary_key = True)

    item_code : Mapped[str] = mapped_column(
        String(100),
        unique = True,
        nullable = False
    )

    name : Mapped[str] = mapped_column(
        String(255),
        nullable = True
    )

    default_specification : Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable = True
    )

    default_unit_of_measurement : Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable = True
    )

    # Free text on purpose. Existing values are offered as suggestions
    # rather than being a fixed list nobody can add to.
    category : Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable = True
    )

    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    is_verified : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    hs_codes : Mapped[list["HsCode"]] = relationship(
        back_populates = "item",
        cascade = "all, delete-orphan"
    )

    consignment_items : Mapped[list["ConsignmentItem"]] = relationship(
        back_populates = "item"
    )

    stock: Mapped[list["Stock"]] = relationship(
    back_populates="item"
    )

    issuances: Mapped[list["Issuance"]] = relationship(
        back_populates="item"
    )
    
    store_requisitions: Mapped[list["StoreRequisition"]] = relationship(
        back_populates="item"
    )
    
    purchases: Mapped[list["PurchasesData"]] = relationship(
        back_populates="item"
    )


#--------------------------------
# HS CODES TABLE
#
# One item can be cleared under several H.S. codes, so they get their
# own table instead of a single column on the item.
#--------------------------------

class HsCode(Base, TimestampMixin):
    __tablename__ = "hs_codes"
    __table_args__ = (
        UniqueConstraint("item_id", "code", name = "unique_hs_code_per_item"),
    )

    id : Mapped[int] = mapped_column(primary_key = True)

    item_id : Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete = "CASCADE"),
        nullable = False
    )

    code : Mapped[str] = mapped_column(
        String(50),
        nullable = False
    )

    # Nothing in this system is ever really deleted. Removing
    # a code from an item only turns it off, the same as every
    # other master. The row stays, so a consignment line that
    # cleared under this code keeps its meaning, and re-adding
    # the code later just switches it back on.
    is_active : Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable = False
    )

    item : Mapped["Item"] = relationship(
        back_populates = "hs_codes"
    )