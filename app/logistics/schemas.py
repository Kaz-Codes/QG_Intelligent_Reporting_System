from pydantic import BaseModel, Field
from typing import Optional
from app.enums import LogisticsStatus, OrderType
from datetime import date
from decimal import Decimal


#------------------------------------
# LOGISTICS CONSIGNMENT (ORDER)
#
# One flat schema for the whole five step wizard, the same way the imports
# module keeps the consignment on one schema. Almost everything is optional
# so a half filled order still saves, matching how imports lets a user
# submit an empty consignment and fill it in later.
#------------------------------------

class LogisticsConsignmentSchema(BaseModel):
    consignment_id: Optional[int] = None

    #--- step 1: order ---
    order_type: Optional[OrderType] = None
    origin_country: Optional[str] = Field(None, max_length=255)
    origin_city: Optional[str] = Field(None, max_length=255)
    origin_province: Optional[str] = Field(None, max_length=255)
    customer_name: Optional[str] = Field(None, max_length=255)
    item_detail: Optional[str] = Field(None, max_length=500)
    quantity: Optional[Decimal] = Field(None, gt=0)
    net_weight: Optional[Decimal] = Field(None, ge=0)
    gross_weight: Optional[Decimal] = Field(None, ge=0)
    idm: Optional[str] = Field(None, max_length=100)
    export_no: Optional[str] = Field(None, max_length=100)
    batch_no: Optional[str] = Field(None, max_length=100)

    #--- step 2: transportation ---
    transporter_name: Optional[str] = Field(None, max_length=255)
    vehicle_type: Optional[str] = Field(None, max_length=100)
    gate_out_date: Optional[date] = None
    dispatch_note_date: Optional[date] = None
    quoted_freight: Optional[Decimal] = Field(None, ge=0)
    actual_freight: Optional[Decimal] = Field(None, ge=0)
    actual_delivery_date: Optional[date] = None
    origin_factory: Optional[str] = Field(None, max_length=255)
    destination: Optional[str] = Field(None, max_length=255)

    #--- step 3: shipping ---
    container_count: Optional[int] = Field(None, ge=0)
    container_type: Optional[str] = Field(None, max_length=100)
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
    remarks: Optional[str] = Field(None, max_length=500)
