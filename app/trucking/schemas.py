from pydantic import BaseModel, Field
from typing import Optional
from app.enums import (
    ContainerType, MovementType, ShiftingType, TruckingPaymentStatus,
    TruckingSource, VehicleTrackingStatus,
)
from datetime import date, datetime
from decimal import Decimal


#------------------------------------
# NESTED REFS AND SNAPSHOTS STORED AS JSON
#
# These small collections are always written whole from the front end, so
# they ride inside their parent row as JSON rather than getting their own
# tables. They reference records in other modules (logistics packages, import
# consignments) by id.
#------------------------------------

class VehiclePackageRefSchema(BaseModel):
    package_id: Optional[str] = None


class VehicleImportRefSchema(BaseModel):
    consignment_id: Optional[str] = None


class TakenSourceSnapshotSchema(BaseModel):
    source_package_id: Optional[str] = None
    label: Optional[str] = None
    item_details: Optional[str] = None
    quantity: Optional[float] = None
    weight: Optional[float] = None


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
    package_refs: Optional[list[VehiclePackageRefSchema]] = []
    import_consignment_refs: Optional[list[VehicleImportRefSchema]] = []


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
    source_ref: Optional[str] = Field(None, max_length=100)
    taken_at: Optional[datetime] = None
    taken_snapshot: Optional[list[TakenSourceSnapshotSchema]] = None
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
    detention: Optional[Decimal] = Field(None, ge=0)

    #--- step 4: tracking ---
    dispatch_note_date: Optional[date] = None
    eta_works: Optional[date] = None
    remarks: Optional[str] = Field(None, max_length=500)

    #--- vehicles ---
    vehicles: Optional[list[TruckingVehicleSchema]] = []
