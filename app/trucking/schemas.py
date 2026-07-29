from pydantic import BaseModel, Field
from typing import Optional
from app.enums import (
    BuiltyStatus, ContainerType, MovementType, ShiftingType, TruckingPaymentStatus,
    TruckingSource, VehicleTrackingStatus,
)
from datetime import date
from decimal import Decimal


#------------------------------------
# TRUCKING VEHICLES
#
# One per truck. The requisition details of a trucking job vary truck by
# truck, so they sit on the vehicle line, the same way item lines carry
# their own fields in imports.
#------------------------------------

class TruckingVehicleSchema(BaseModel):
    id: Optional[int] = None
    vehicle_number: Optional[str] = Field(None, max_length=50)
    vehicle_type: Optional[str] = Field(None, max_length=100)
    no_of_packages: Optional[int] = Field(None, ge=0)
    driver_phone: Optional[str] = Field(None, max_length=50)
    net_weight: Optional[Decimal] = Field(None, ge=0)
    gross_weight: Optional[Decimal] = Field(None, ge=0)
    container_no: Optional[str] = Field(None, max_length=100)
    container_type: Optional[ContainerType] = None
    tracking_status: Optional[VehicleTrackingStatus] = None
    builty_status: Optional[BuiltyStatus] = None


#------------------------------------
# TRUCKING CONSIGNMENTS (JOBS)
#
# One flat schema for the whole four step wizard, plus the repeating
# vehicles, the same way the imports consignment carries its item lines.
# Almost everything is optional so a half filled job still saves.
#------------------------------------

class TruckingConsignmentSchema(BaseModel):
    consignment_id: Optional[int] = None

    #--- step 1: movement and item ---
    movement_type: Optional[MovementType] = None
    source: Optional[TruckingSource] = None
    execution_date: Optional[date] = None
    transporter_name: Optional[str] = Field(None, max_length=255)
    shifting_type: Optional[ShiftingType] = None
    item_details: Optional[str] = Field(None, max_length=500)
    pickup: Optional[str] = Field(None, max_length=255)
    destination: Optional[str] = Field(None, max_length=255)
    reference_no: Optional[str] = Field(None, max_length=100)

    #--- step 3: freight and payment ---
    quoted_freight: Optional[Decimal] = Field(None, ge=0)
    actual_freight: Optional[Decimal] = Field(None, ge=0)
    payment_status: Optional[TruckingPaymentStatus] = None
    paid_amount: Optional[Decimal] = Field(None, ge=0)

    #--- step 4: tracking ---
    dispatch_note_date: Optional[date] = None
    eta_works: Optional[date] = None
    remarks: Optional[str] = Field(None, max_length=500)

    #--- vehicles ---
    vehicles: Optional[list[TruckingVehicleSchema]] = []
