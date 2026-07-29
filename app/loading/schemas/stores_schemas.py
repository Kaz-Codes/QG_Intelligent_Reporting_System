from datetime import date
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.masters.models import Item


# =====================================================
# STOCK
# =====================================================

class Stock(Base):
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    item_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("items.item_code"),
        nullable=True
    )

    item_name: Mapped[Optional[str]] = mapped_column(Text)

    branch: Mapped[Optional[str]] = mapped_column(Text)

    hold_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    stock_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    stock_qty_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 2)
    )

    available_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    available_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 2)
    )

    item: Mapped[Optional["Item"]] = relationship(
        back_populates="stock"
    )


# =====================================================
# ISSUANCE
# =====================================================

class Issuance(Base):
    __tablename__ = "issuance"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    issuance_code: Mapped[Optional[str]] = mapped_column(
        Text,
        unique=True
    )

    item_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("items.item_code"),
        nullable=True
    )

    item_name: Mapped[Optional[str]] = mapped_column(Text)

    specification: Mapped[Optional[str]] = mapped_column(Text)

    department: Mapped[Optional[str]] = mapped_column(Text)

    branch: Mapped[Optional[str]] = mapped_column(Text)

    issue_to_others: Mapped[Optional[str]] = mapped_column(Text)

    authorized_by: Mapped[Optional[str]] = mapped_column(Text)

    issued_by: Mapped[Optional[str]] = mapped_column(Text)

    received_by: Mapped[Optional[str]] = mapped_column(Text)

    description: Mapped[Optional[str]] = mapped_column(Text)

    ref_no: Mapped[Optional[str]] = mapped_column(Text)

    demand_ref_no: Mapped[Optional[str]] = mapped_column(Text)

    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    status: Mapped[Optional[str]] = mapped_column(Text)

    from_date: Mapped[Optional[date]] = mapped_column(Date)

    unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    total_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 2)
    )

    job_number: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped[Optional["Item"]] = relationship(
        back_populates="issuances"
    )


# =====================================================
# STORE REQUISITION
# =====================================================

class StoreRequisition(Base):
    __tablename__ = "store_requisition"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    item_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("items.item_code"),
        nullable=True
    )

    item_name: Mapped[Optional[str]] = mapped_column(Text)

    ref_no: Mapped[Optional[str]] = mapped_column(Text)

    department: Mapped[Optional[str]] = mapped_column(Text)

    branch: Mapped[Optional[str]] = mapped_column(Text)

    prepare_date: Mapped[Optional[date]] = mapped_column(Date)

    description: Mapped[Optional[str]] = mapped_column(Text)

    required_by: Mapped[Optional[str]] = mapped_column(Text)

    req_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    pur_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    pending_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    last_purchase: Mapped[Optional[date]] = mapped_column(Date)

    previous_price: Mapped[Optional[str]] = mapped_column(Text)

    required_date: Mapped[Optional[date]] = mapped_column(Date)

    status: Mapped[Optional[str]] = mapped_column(Text)

    sourced_by: Mapped[Optional[str]] = mapped_column(Text)

    previous_supplier: Mapped[Optional[str]] = mapped_column(Text)

    original_required_date: Mapped[Optional[date]] = mapped_column(Date)

    stock_in_date: Mapped[Optional[date]] = mapped_column(Date)

    item: Mapped[Optional["Item"]] = relationship(
        back_populates="store_requisitions"
    )


# =====================================================
# PURCHASES DATA
# =====================================================

class PurchasesData(Base):
    __tablename__ = "purchases_data"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    item_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("items.item_code"),
        nullable=True
    )

    item_name: Mapped[Optional[str]] = mapped_column(Text)

    specification: Mapped[Optional[str]] = mapped_column(Text)

    po_number: Mapped[Optional[str]] = mapped_column(Text)

    po_date: Mapped[Optional[date]] = mapped_column(Date)

    ref_no: Mapped[Optional[str]] = mapped_column(Text)

    qty: Mapped[Optional[int]] = mapped_column()

    branch: Mapped[Optional[str]] = mapped_column(Text)

    amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3)
    )

    ppc_store: Mapped[Optional[date]] = mapped_column(Date)

    required_d: Mapped[Optional[date]] = mapped_column(Date)

    purchase: Mapped[Optional[date]] = mapped_column(Date)

    mop: Mapped[Optional[str]] = mapped_column(Text)

    dc_no: Mapped[Optional[str]] = mapped_column(Text)

    bill_no: Mapped[Optional[str]] = mapped_column(Text)

    sourcing_o: Mapped[Optional[str]] = mapped_column(Text)

    supplier: Mapped[Optional[str]] = mapped_column(Text)

    item: Mapped[Optional["Item"]] = relationship(
        back_populates="purchases"
    )