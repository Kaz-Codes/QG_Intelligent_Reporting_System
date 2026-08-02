from pydantic import BaseModel, Field
from typing import Optional
from app.enums import (
    LogisticsStatus, OrderType, Department, Incoterm, PackingStatus,
)
from datetime import date
from decimal import Decimal


#------------------------------------
# NESTED FEEDS STORED AS JSON
#
# These three collections are always written as a whole from the front end,
# so they ride along inside their parent row as JSON rather than getting their
# own tables. They are validated here only for shape; the values are kept as
# the strings/numbers JSON can hold (dates stay ISO strings).
#------------------------------------

class RfdChangeEventSchema(BaseModel):
    id: Optional[str] = None
    field: Optional[str] = None
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: Optional[str] = None
    changed_at: Optional[str] = None
    remark: Optional[str] = None


class PackageAllocationSchema(BaseModel):
    id: Optional[str] = None
    item_id: Optional[str] = None
    # The order (batch) that owns the allocated item. Equal to this order's id
    # for a local item, a sibling batch's id for a cross-batch reference.
    source_order_id: Optional[str] = None
    quantity: Optional[float] = Field(None, ge=0)


class RemarkEntrySchema(BaseModel):
    id: Optional[str] = None
    text: Optional[str] = None
    authored_by: Optional[str] = None
    authored_at: Optional[str] = None
    system: Optional[bool] = False


#------------------------------------
# LOGISTICS ITEMS
#
# One per item. Net weight (quantity x unit weight) is derived on the front
# end and never sent. rfd_history is the per-item change feed.
#------------------------------------

class LogisticsItemSchema(BaseModel):
    id: Optional[int] = None
    job_no: Optional[str] = Field(None, max_length=100)
    item_detail: Optional[str] = Field(None, max_length=500)
    quantity: Optional[Decimal] = Field(None, ge=0)
    unit_weight: Optional[Decimal] = Field(None, ge=0)
    gross_weight: Optional[Decimal] = Field(None, ge=0)
    planned_rfd_date: Optional[date] = None
    actual_rfd_date: Optional[date] = None
    rfd_history: Optional[list[RfdChangeEventSchema]] = []


#------------------------------------
# LOGISTICS PACKAGES
#
# One per physical package, with a per-item allocation feed.
#------------------------------------

class LogisticsPackageSchema(BaseModel):
    id: Optional[int] = None
    colour_code: Optional[str] = Field(None, max_length=100)
    packing_works: Optional[str] = Field(None, max_length=255)
    packing_ready_date: Optional[date] = None
    packing_date: Optional[date] = None
    quoted_packing_cost: Optional[Decimal] = Field(None, ge=0)
    actual_packing_cost: Optional[Decimal] = Field(None, ge=0)
    gross_weight: Optional[Decimal] = Field(None, ge=0)
    status: Optional[PackingStatus] = None
    allocations: Optional[list[PackageAllocationSchema]] = []


#------------------------------------
# LOGISTICS CONTAINERS
#------------------------------------

class LogisticsContainerSchema(BaseModel):
    id: Optional[int] = None
    container_no: Optional[str] = Field(None, max_length=100)
    container_type: Optional[str] = Field(None, max_length=100)


#------------------------------------
# LOGISTICS CONSIGNMENT (ORDER)
#
# One flat schema for the whole five step wizard plus the repeating item,
# package and container lines, the same way the imports module carries its
# item and payment lines. Almost everything is optional so a half filled
# order still saves.
#------------------------------------

class LogisticsConsignmentSchema(BaseModel):
    consignment_id: Optional[int] = None

    #--- step 1: order ---
    order_type: Optional[OrderType] = None
    department: Optional[Department] = None
    origin_country: Optional[str] = Field(None, max_length=255)
    origin_city: Optional[str] = Field(None, max_length=255)
    origin_province: Optional[str] = Field(None, max_length=255)
    customer_name: Optional[str] = Field(None, max_length=255)
    mo_no: Optional[str] = Field(None, max_length=100)
    batch_no: Optional[int] = Field(None, ge=1)
    batch_label: Optional[str] = Field(None, max_length=100)
    incoterm: Optional[Incoterm] = None

    #--- step 3: shipping ---
    pol: Optional[str] = Field(None, max_length=255)
    pod: Optional[str] = Field(None, max_length=255)
    shipping_line: Optional[str] = Field(None, max_length=255)
    clearing_agent: Optional[str] = Field(None, max_length=255)
    booking_no: Optional[str] = Field(None, max_length=100)
    port_in_date: Optional[date] = None
    etd_sailing_date: Optional[date] = None
    cro_arrival_date: Optional[date] = None
    actual_arrival_date: Optional[date] = None

    #--- step 4: expenditures ---
    packing_cost: Optional[Decimal] = Field(None, ge=0)
    transportation_charges: Optional[Decimal] = Field(None, ge=0)
    container_detention: Optional[Decimal] = Field(None, ge=0)
    insurance: Optional[Decimal] = Field(None, ge=0)
    trucking_lhr_to_khi: Optional[Decimal] = Field(None, ge=0)
    fumigation_cost: Optional[Decimal] = Field(None, ge=0)
    lashing: Optional[Decimal] = Field(None, ge=0)
    qfl_charges: Optional[Decimal] = Field(None, ge=0)
    qfl_container_movement: Optional[Decimal] = Field(None, ge=0)
    custom_clearance_charges: Optional[Decimal] = Field(None, ge=0)
    port_charges: Optional[Decimal] = Field(None, ge=0)
    dhl_charges: Optional[Decimal] = Field(None, ge=0)
    sea_air_freight: Optional[Decimal] = Field(None, ge=0)

    #--- step 5: status and remarks ---
    current_status: Optional[LogisticsStatus] = None
    effective_date: Optional[date] = None
    gate_out_date: Optional[date] = None
    sent_to_trucking: Optional[bool] = None
    remarks_log: Optional[list[RemarkEntrySchema]] = None

    #--- lines ---
    items: Optional[list[LogisticsItemSchema]] = []
    packages: Optional[list[LogisticsPackageSchema]] = []
    containers: Optional[list[LogisticsContainerSchema]] = []
