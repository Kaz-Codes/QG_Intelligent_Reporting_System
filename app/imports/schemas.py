from pydantic import BaseModel, Field
from typing import Optional
from app.enums import (
    ConsignmentType, Currency, ModeOfShipment, PaymentInstrument,
    PaymentStatus, RateSource, RequisitionType, Status, UnitOfMeasurement,
)
from datetime import date
from decimal import Decimal


#------------------------------------
# CONSIGNMENT ITEMS
#------------------------------------

class ConsignmentItemSchema(BaseModel):
    id : Optional[int] = None
    item_id : Optional[int] = None
    item_name : Optional[str] = Field(None, max_length=255)
    item_code : Optional[str] = Field(None, max_length=100)
    hs_code : Optional[str] = Field(None, max_length=50)
    specification : Optional[str] = Field(None, max_length=500)
    quantity : Optional[Decimal] = Field(None, gt=0)
    unit_of_measurement : Optional[UnitOfMeasurement] = None
    batch_no : Optional[str] = Field(None, max_length=100)
    requisition_type : Optional[RequisitionType] = None
    unit_price : Optional[Decimal] = Field(None, gt=0)
    elc : Optional[Decimal] = Field(None, ge=0)
    alc : Optional[Decimal] = Field(None, ge=0)
    reference_number : Optional[str] = Field(None, max_length=100)
    job_number : Optional[str] = Field(None, max_length=100)
    mo_number : Optional[str] = Field(None, max_length=100)
    description : Optional[str] = Field(None, max_length=500)


#------------------------------------
# CONSIGNMENT PAYMETNS
#------------------------------------

class ConsignmentPaymentSchema(BaseModel):
    id : Optional[int] = None
    retirement_date : Optional[date] = None
    value : Optional[Decimal] = Field(None, gt=0)
    payment_exchange_rate : Optional[Decimal] = Field(None, gt=0)
    bank_charges : Optional[Decimal] = Field(None, ge=0)
    status : Optional[PaymentStatus] = None
    bank_reference : Optional[str] = Field(None, max_length=100)


#------------------------------------
# CONSIGNMENS
#------------------------------------

class ConsignmentSchema(BaseModel):
    #---consignment---
    consignment_id : Optional[int] = None
    branch_id : Optional[int] = None 
    supplier_id : Optional[int] = None
    origin : Optional[str] = Field(None, max_length=255)
    currency : Optional[Currency] = None
    consignment_type : Optional[ConsignmentType] = None
    po_date : Optional[date] = None
    requisition_date : Optional[date] = None

    #---finance---
    payment_instrument : Optional[PaymentInstrument] = None
    instrument_number : Optional[str] = Field(None, max_length=100)
    opening_or_retirement_date : Optional[date] = None
    works : Optional[str] = Field(None, max_length=255)
    exchange_rate : Optional[Decimal] = Field(None, ge = 0)
    rate_booked_on : Optional[date] = None
    rate_source : Optional[RateSource] = None
    #---shipping---
    mode_of_shipment : Optional[ModeOfShipment] = None
    loading_port_id : Optional[int] = None
    delivery_port_id : Optional[int] = None
    cargo_readiness_date : Optional[date] = None
    etd : Optional[date] = None
    eta : Optional[date] = None
    eta_works : Optional[date] = None
    cause_of_revision : Optional[str] = None
    #---status and remarks---
    current_status : Optional[Status] = None
    effective_date : Optional[date] = None
    remarks : Optional[str] = Field(None, max_length=500)
    #---clearence
    clearing_agent_id : Optional[int] = None
    gd_number : Optional[str] = Field(None, max_length=100)
    gd_filing_date : Optional[date] = None
    free_days_allowed : Optional[int] = Field(None, ge = 0)
    gate_out_date : Optional[date] = None
    demurrage_or_detention_paid : Optional[Decimal] = Field(None, ge = 0)
    #---items and payments---
    items : Optional[list[ConsignmentItemSchema]] = []
    payments : Optional[list[ConsignmentPaymentSchema]] = []