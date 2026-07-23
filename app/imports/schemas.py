from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.enums import (
    ConsignmentType, Currency, ModeOfShipment, PaymentInstrument,
    PaymentStatus, RateSource, RequisitionType, Status, UnitOfMeasurement,
)

#-----------------------------------------------------
# WHAT THE IMPORTS APIS ACCEPT
#
# The wizard is seven steps and every step saves on its own,
# so there is one schema per step instead of one big schema
# for the whole consignment. A user who fills in half of
# step three and walks away still gets that half saved.
#
# Almost everything is Optional. The excel sheet this
# replaces is filled in over weeks, not in one sitting, so
# refusing a half filled form would make the system unusable.
# Only the fields the database itself insists on are required.
#-----------------------------------------------------


#--------------------------------
# ITEM LINES (STEP 1)
#
# Requisition details sit here and not on the consignment
# because one consignment can carry a Store item and an
# Engineering item together.
#--------------------------------

class ConsignmentItemSchema(BaseModel):
    item_id : Optional[int] = None

    item_code : str = Field(..., max_length=100)
    item_name : str = Field(..., max_length=255)
    specification : Optional[str] = Field(None, max_length=500)
    hs_code : Optional[str] = Field(None, max_length=50)

    quantity : Decimal = Field(..., ge=0)
    unit_price : Optional[Decimal] = Field(None, ge=0)
    unit_of_measurement : Optional[UnitOfMeasurement] = None
    batch_no : Optional[str] = Field(None, max_length=100)

    requisition_type : Optional[RequisitionType] = None
    reference_number : Optional[str] = Field(None, max_length=100)
    job_number : Optional[str] = Field(None, max_length=100)
    mo_number : Optional[str] = Field(None, max_length=100)
    description : Optional[str] = Field(None, max_length=500)


#--------------------------------
# ITEM LINE EDIT
#
# Same fields, all optional, so the frontend can send only
# what the user actually touched on the inline edit.
#--------------------------------

class ConsignmentItemUpdateSchema(BaseModel):
    item_id : Optional[int] = None

    item_code : Optional[str] = Field(None, max_length=100)
    item_name : Optional[str] = Field(None, max_length=255)
    specification : Optional[str] = Field(None, max_length=500)
    hs_code : Optional[str] = Field(None, max_length=50)

    quantity : Optional[Decimal] = Field(None, ge=0)
    unit_price : Optional[Decimal] = Field(None, ge=0)
    unit_of_measurement : Optional[UnitOfMeasurement] = None
    batch_no : Optional[str] = Field(None, max_length=100)

    requisition_type : Optional[RequisitionType] = None
    reference_number : Optional[str] = Field(None, max_length=100)
    job_number : Optional[str] = Field(None, max_length=100)
    mo_number : Optional[str] = Field(None, max_length=100)
    description : Optional[str] = Field(None, max_length=500)


#--------------------------------
# STEP 1 : CONSIGNMENT
#
# The header plus the item lines. This is the only call
# that creates a consignment, everything after it updates
# one that already exists.
#--------------------------------

class ConsignmentSchema(BaseModel):
    branch_id : Optional[int] = None
    supplier_id : Optional[int] = None

    origin : Optional[str] = Field(None, max_length=255)
    currency : Optional[Currency] = None
    consignment_type : Optional[ConsignmentType] = None
    po_date : Optional[date] = None

    items : list[ConsignmentItemSchema] = []


#--------------------------------
# STEP 2 : FINANCE
#
# The exchange rate is booked here together with the date it
# was taken and where it came from. An old consignment is
# never re converted at today's rate.
#
# item_prices is a list of {item_id, unit_price} so the
# pricing table can be saved in one call.
#--------------------------------

class ItemPriceSchema(BaseModel):
    item_id : int
    unit_price : Optional[Decimal] = Field(None, ge=0)


class FinanceSchema(BaseModel):
    payment_instrument : Optional[PaymentInstrument] = None
    instrument_number : Optional[str] = Field(None, max_length=100)
    opening_or_retirement_date : Optional[date] = None
    works_id : Optional[int] = None

    exchange_rate : Optional[Decimal] = Field(None, ge=0)
    rate_booked_on : Optional[date] = None
    rate_source : Optional[RateSource] = None

    item_prices : list[ItemPriceSchema] = []


#--------------------------------
# STEP 3 : SHIPPING
#
# Changing the ETA never overwrites the old one on its own.
# When a new eta arrives a row is appended to the revision
# history, which is why a cause is asked for here.
#--------------------------------

class ShippingSchema(BaseModel):
    mode_of_shipment : Optional[ModeOfShipment] = None
    loading_port_id : Optional[int] = None
    delivery_port_id : Optional[int] = None

    cargo_readiness_date : Optional[date] = None
    etd : Optional[date] = None
    eta : Optional[date] = None
    eta_works : Optional[date] = None

    cause_of_revision : Optional[str] = Field(None, max_length=500)


#--------------------------------
# STEP 4 : PAYMENTS
#
# Partial payments are normal so these are separate rows,
# not columns on the consignment. Each payment carries its
# own rate because instalments months apart settle at
# different rates. Leave it blank to fall back to the rate
# booked on the consignment.
#--------------------------------

class PaymentSchema(BaseModel):
    retirement_date : Optional[date] = None
    value : Optional[Decimal] = Field(None, ge=0)
    exchange_rate : Optional[Decimal] = Field(None, ge=0)
    bank_charges : Optional[Decimal] = Field(None, ge=0)
    status : Optional[PaymentStatus] = None
    bank_reference : Optional[str] = Field(None, max_length=100)


#--------------------------------
# STEP 5 : STATUS
#
# effective_date is the day the stage actually changed,
# which is usually not the day somebody got round to
# entering it. Clearance timing counts from the effective
# date of the "Arrived at port" row.
#--------------------------------

class StatusChangeSchema(BaseModel):
    new_status : Status
    effective_date : date
    remarks : Optional[str] = Field(None, max_length=500)


#--------------------------------
# STEP 6 : CLEARANCE
#--------------------------------

class ClearanceSchema(BaseModel):
    clearing_agent_id : Optional[int] = None
    gd_number : Optional[str] = Field(None, max_length=100)
    gd_filing_date : Optional[date] = None
    free_days_allowed : Optional[int] = Field(None, ge=0)
    gate_out_date : Optional[date] = None
    demurrage_or_detention_paid : Optional[Decimal] = Field(None, ge=0)


#--------------------------------
# STEP 7 : LANDED COST
#
# Estimated and actual landed cost are typed in by hand per
# item, in PKR. Nothing in this system works them out. Duty,
# freight and agent fees are not tracked anywhere here.
#--------------------------------

class LandedCostItemSchema(BaseModel):
    item_id : int
    elc : Optional[Decimal] = Field(None, ge=0)
    alc : Optional[Decimal] = Field(None, ge=0)


class LandedCostSchema(BaseModel):
    items : list[LandedCostItemSchema] = []
