from typing import Optional

from pydantic import BaseModel, Field

from app.enums import Currency, PortType, PortUsedAs, UnitOfMeasurement

#-----------------------------------------------------
# WHAT THE MASTERS APIS ACCEPT
#
# One create schema and one update schema per master.
# The field names match the model columns on purpose, so a
# route can hand the whole thing to the model in one line
# instead of copying twenty fields across by hand.
#
# On create only the columns the database itself insists on
# are required. On update everything is optional, so the
# edit drawer can send only what the user actually changed.
#-----------------------------------------------------


#--------------------------------
# SUPPLIER
#--------------------------------

class SupplierCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)
    country : str = Field(..., max_length=255)
    city : Optional[str] = Field(None, max_length=255)
    contact_name : Optional[str] = Field(None, max_length=255)
    phone : Optional[str] = Field(None, max_length=50)
    email : Optional[str] = Field(None, max_length=255)
    default_currency : Optional[Currency] = None
    default_payment_terms : Optional[str] = Field(None, max_length=255)


class SupplierUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)
    country : Optional[str] = Field(None, max_length=255)
    city : Optional[str] = Field(None, max_length=255)
    contact_name : Optional[str] = Field(None, max_length=255)
    phone : Optional[str] = Field(None, max_length=50)
    email : Optional[str] = Field(None, max_length=255)
    default_currency : Optional[Currency] = None
    default_payment_terms : Optional[str] = Field(None, max_length=255)


#--------------------------------
# BRANCH
#
# Never created inline, so there is no separate inline
# schema. It has to exist before a consignment can point at
# it.
#--------------------------------

class BranchCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)
    code : Optional[str] = Field(None, max_length=50)
    city : Optional[str] = Field(None, max_length=255)
    address : Optional[str] = Field(None, max_length=500)


class BranchUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)
    code : Optional[str] = Field(None, max_length=50)
    city : Optional[str] = Field(None, max_length=255)
    address : Optional[str] = Field(None, max_length=500)


#--------------------------------
# WORKS
#--------------------------------

class WorksCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)
    code : Optional[str] = Field(None, max_length=50)
    ntn_strn : Optional[str] = Field(None, max_length=100)
    note : Optional[str] = Field(None, max_length=500)


class WorksUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)
    code : Optional[str] = Field(None, max_length=50)
    ntn_strn : Optional[str] = Field(None, max_length=100)
    note : Optional[str] = Field(None, max_length=500)


#--------------------------------
# PORT
#
# A port needs its Sea/Air type even when it is created in
# the middle of data entry, because the shipping step
# filters ports by mode and cannot do that without it.
#--------------------------------

class PortCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)
    country : Optional[str] = Field(None, max_length=255)
    port_type : PortType = PortType.SEA
    un_locode : Optional[str] = Field(None, max_length=20)
    used_as : PortUsedAs = PortUsedAs.BOTH


class PortUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)
    country : Optional[str] = Field(None, max_length=255)
    port_type : Optional[PortType] = None
    un_locode : Optional[str] = Field(None, max_length=20)
    used_as : Optional[PortUsedAs] = None


#--------------------------------
# CLEARING AGENT
#--------------------------------

class ClearingAgentCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)
    licence_no : Optional[str] = Field(None, max_length=100)
    contact_name : Optional[str] = Field(None, max_length=255)
    phone : Optional[str] = Field(None, max_length=50)
    primary_port_id : Optional[int] = None


class ClearingAgentUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)
    licence_no : Optional[str] = Field(None, max_length=100)
    contact_name : Optional[str] = Field(None, max_length=255)
    phone : Optional[str] = Field(None, max_length=50)
    primary_port_id : Optional[int] = None


#--------------------------------
# CUSTOMER
#
# Name only, by decision. The logistics workbooks carry nothing else about a
# customer, so there is nothing to populate address or contact columns with.
#--------------------------------

class CustomerCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)


class CustomerUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)


#--------------------------------
# TRANSPORTER
#--------------------------------

class TransporterCreateSchema(BaseModel):
    name : str = Field(..., max_length=255)
    contact_name : Optional[str] = Field(None, max_length=255)
    phone : Optional[str] = Field(None, max_length=50)
    ntn : Optional[str] = Field(None, max_length=100)


class TransporterUpdateSchema(BaseModel):
    name : Optional[str] = Field(None, max_length=255)
    contact_name : Optional[str] = Field(None, max_length=255)
    phone : Optional[str] = Field(None, max_length=50)
    ntn : Optional[str] = Field(None, max_length=100)


#--------------------------------
# ITEM
#
# One item can be cleared under several H.S. codes, so they
# come in as a list and get their own rows in the hs_codes
# table rather than a single column on the item.
#
# Category is free text on purpose. Existing values are
# offered as suggestions rather than being a fixed list
# nobody can add to.
#--------------------------------

class ItemCreateSchema(BaseModel):
    item_code : str = Field(..., max_length=100)
    name : str = Field(..., max_length=255)
    default_specification : Optional[str] = Field(None, max_length=500)
    default_unit_of_measurement : Optional[UnitOfMeasurement] = None
    category : Optional[str] = Field(None, max_length=255)
    hs_codes : list[str] = []


class ItemUpdateSchema(BaseModel):
    item_code : Optional[str] = Field(None, max_length=100)
    name : Optional[str] = Field(None, max_length=255)
    default_specification : Optional[str] = Field(None, max_length=500)
    default_unit_of_measurement : Optional[UnitOfMeasurement] = None
    category : Optional[str] = Field(None, max_length=255)
    # Left as None means "do not touch the H.S. codes". An
    # empty list means "the item now has none".
    hs_codes : Optional[list[str]] = None
