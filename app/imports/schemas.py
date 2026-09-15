from pydantic import BaseModel, Field
from typing import Optional
from app.enums import (
    ConsignmentType, Currency, Incoterm, ModeOfShipment, PaymentInstrument,
    PaymentStatus, PriceBasis, RateSource, RequisitionType, Status,
    UnitOfMeasurement,
)
from datetime import date
from decimal import Decimal


#------------------------------------
# CONSIGNMENT ITEMS
#------------------------------------

class ConsignmentItemSchema(BaseModel):
    id : Optional[int] = None

    # WHICH ORDER LINE THIS SHIPMENT LINE ALLOCATES AGAINST.
    #
    # Optional, and absent from everything the wizard currently sends: a line
    # with no `order_item_id` either keeps the order line it already has or
    # gets a new one, which is exactly today's behaviour. It is needed only
    # when a LATER batch allocates against an order line that already exists,
    # and the server validates that the line belongs to this order (see
    # helpers.resolve_order_line) rather than trusting it.
    order_item_id : Optional[int] = None

    # WHAT THE ORDER BOUGHT, as opposed to what this batch carries.
    #
    # Also optional, and for the same reason: while an order holds one batch
    # the two are the same quantity, so leaving it out means "the same as
    # `quantity`" and the current wizard needs no change before step 8. Once an
    # order has split they are different facts and this is the one that can no
    # longer be inferred - see helpers.resolve_ordered_quantity.
    #
    # `ge=0`, not `gt=0` like `quantity`: the migration's COALESCE rows sit at
    # zero and have to be expressible so they can be corrected. Allocating
    # against one is refused at the server, with a message naming that fix.
    ordered_quantity : Optional[Decimal] = Field(None, ge=0)

    item_id : Optional[int] = None
    item_name : Optional[str] = Field(None, max_length=255)
    # The operator's informal label for the line (see the model). Pydantic
    # drops anything not declared here, so without this the field never
    # reaches ConsignmentItem(**item_dict) and is silently discarded on save.
    placeholder_name : Optional[str] = Field(None, max_length=255)
    item_code : Optional[str] = Field(None, max_length=100)
    hs_code : Optional[str] = Field(None, max_length=50)
    specification : Optional[str] = Field(None, max_length=500)
    quantity : Optional[Decimal] = Field(None, gt=0)
    unit_of_measurement : Optional[UnitOfMeasurement] = None
    batch_no : Optional[str] = Field(None, max_length=100)
    requisition_type : Optional[RequisitionType] = None
    unit_price : Optional[Decimal] = Field(None, gt=0)

    # HOW THIS LINE IS PRICED - enums.PriceBasis, design revision 14.
    #
    # `quantity` -> quantity x unit_price
    # `weight`   -> quantity x unit_weight x weight_unit_price
    #
    # The two prices are separate columns rather than one meaning two things,
    # so summing a column of unit prices never mixes rupees-per-kg with
    # rupees-per-piece (enums.py). WHICHEVER BASIS IS CHOSEN, THE OTHER PRICE
    # IS NOT READ - a stored value in the unused field is inert, which is why
    # the wizard hides it rather than leaving a number nothing multiplies.
    price_basis : Optional[PriceBasis] = None
    # Per KILOGRAM. `gt=0` like unit_price: a zero price is not a price.
    weight_unit_price : Optional[Decimal] = Field(None, gt=0)
    # Kilograms PER UNIT - deliberately not the line's total, which is
    # ConsignmentItem.net_weight. Multiplying quantity by a total would count
    # the quantity twice.
    unit_weight : Optional[Decimal] = Field(None, gt=0)
    # Weight & dimensions — optional at draft (see model comment).
    net_weight : Optional[Decimal] = Field(None, ge=0)
    gross_weight : Optional[Decimal] = Field(None, ge=0)
    length : Optional[Decimal] = Field(None, ge=0)
    width : Optional[Decimal] = Field(None, ge=0)
    height : Optional[Decimal] = Field(None, ge=0)
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
    incoterm : Optional[Incoterm] = None
    po_date : Optional[date] = None
    requisition_date : Optional[date] = None
    required_date : Optional[date] = None

    #---finance---
    payment_instrument : Optional[PaymentInstrument] = None
    instrument_number : Optional[str] = Field(None, max_length=100)
    opening_or_retirement_date : Optional[date] = None
    works : Optional[str] = Field(None, max_length=255)
    exchange_rate : Optional[Decimal] = Field(None, ge = 0)
    rate_booked_on : Optional[date] = None
    rate_source : Optional[RateSource] = None
    # LC-level, entered on Step 4 beside the payments. `ge=0` rather than `gt=0`
    # - an order can genuinely carry no insurance, and 0 says so where NULL says
    # "nobody has looked".
    insurance_amount : Optional[Decimal] = Field(None, ge=0)
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
    container_detention : Optional[Decimal] = Field(None, ge = 0)
    #---items and payments---
    items : Optional[list[ConsignmentItemSchema]] = []
    payments : Optional[list[ConsignmentPaymentSchema]] = []


#------------------------------------
# ADDING A BATCH TO AN EXISTING ORDER
#
# DELIBERATELY THIN. A batch is created by saying which of the order's items
# this arrival brings and how much of each; everything else about it - the
# route, the schedule, the ports, the clearance, the status - is entered
# afterwards through the ordinary edit, because the requirements are explicit
# that a later batch's shipping section starts empty and editable.
#
# Nothing commercial appears here at all: supplier, currency, incoterm and the
# booked rate are the ORDER's and the new batch reads the same row its siblings
# do. A field for any of them would be a second place to set a value that has
# exactly one home.
#------------------------------------

class BatchAllocationSchema(BaseModel):
    order_item_id : int
    # `gt=0`: a batch that carries nothing of an item is a batch that does not
    # carry it, which is expressed by leaving the line out.
    quantity : Decimal = Field(gt=0)


class CreateBatchSchema(BaseModel):
    # At least one line, for the same reason the empty-draft guard exists on
    # create: a batch carrying nothing is not a shipment, and creating one
    # would put a row into every list and count with nothing in it.
    allocations : list[BatchAllocationSchema] = Field(min_length=1)