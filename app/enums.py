from enum import Enum

#-----------------------------------------------------
# FIXED LISTS
#
# These change once in a decade, so they live in code rather than in a
# database table that nobody would ever maintain.
#
# They inherit from str as well as Enum, so FastAPI and Pydantic accept
# and return them as plain strings without any conversion.
#
# The columns that use them are stored as String, not as a database
# enum type. Adding a new status is then a one-line change here instead
# of an ALTER TYPE migration.
#-----------------------------------------------------


#--------------------------------
# CURRENCY
#--------------------------------

class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    CNY = "CNY"
    JPY = "JPY"
    GBP = "GBP"
    AED = "AED"

#--------------------------------
# UNIT OF MEASUREMENT
#--------------------------------

class UnitOfMeasurement(str, Enum):
    PCS = "Pcs"
    SET = "Set"
    PAIR = "Pair"
    ROLL = "Roll"
    BOX = "Box"
    CARTON = "Carton"
    DRUM = "Drum"
    PALLET = "Pallet"
    KG = "Kg"
    GRAM = "Gram"
    TON = "Ton"
    LB = "Lb"
    METRE = "Metre"
    CENTIMETRE = "Centimetre"
    FOOT = "Foot"
    INCH = "Inch"
    SQ_METRE = "Sq. metre"
    CU_METRE = "Cu. metre"
    LITRE = "Litre"


#--------------------------------
# PORTS
#--------------------------------

class PortType(str, Enum):
    SEA = "Sea"
    AIR = "Air"
    DRY = "Dry"
    LAND = "Land"


class PortUsedAs(str, Enum):
    LOADING = "Loading"
    DELIVERY = "Delivery"
    BOTH = "Both"


#--------------------------------
# THE ELEVEN STAGES GOODS MOVE THROUGH
#
# The order here is the order they actually happen in. Do not reorder
# it, because reports depend on the sequence.
#--------------------------------

class Status(str, Enum):
    TT_LC_IN_PROCESS = "TT/LC in Process"
    UNDER_PRODUCTION = "Under Production"
    READY_AWAITING_SAILING = "Ready Awaiting Sailing"
    IN_TRANSIT = "In Transit"
    ARRIVED_AT_PORT = "Arrived at Port"
    UNDER_CUSTOM_CLEARANCE = "Under Custom Clearance"
    UNDER_EXAMINATION = "Under Examination"
    UNDER_ASSESSMENT = "Under Assessment"
    # Unstuffing the container, after assessment and before the goods move on.
    # Came from the imported sheets; added here because it is a real stage with
    # no equivalent among the others, not a spelling of one.
    UNDER_DE_STUFFING = "Under De-Stuffing"
    ARRIVED_AT_QFL = "Arrived at QFL"
    ON_ROAD = "On Road"
    ARRIVED_AT_WORKS = "Arrived at Works"
    # A terminal state that is NOT an arrival: the import never completes. Last
    # in the list because it is an exit, not a later stage. Note this does not
    # lock a record — only "Arrived at Works" does (see helpers.is_closed).
    ORDER_CANCELLED = "Order Cancelled"


#--------------------------------
# WHERE THE EXCHANGE RATE CAME FROM
# Needed to reconcile a consignment against a bank advice later.
#--------------------------------

class RateSource(str, Enum):
    BANK_LC = "Bank LC opening rate"
    BANK_TT = "Bank TT rate"
    SBP_INTERBANK = "SBP inter bank"
    CONTRACT_OR_AGREED = "Contract/agreed rate"


#--------------------------------
# SHIPPING AND CONSIGNMENT TYPE
#--------------------------------

class ModeOfShipment(str, Enum):
    SEA_FREIGHT_FCL = "Sea freight FCL"
    SEA_FREIGHT_LCL = "Sea freight LCL"
    AIR_FREIGHT = "Air freight"
    LAND_OR_COURIER = "Land/courier"


class ConsignmentType(str, Enum):
    EFS = "EFS"
    REGULAR_IMPORT = "Regular import"


#--------------------------------
# PAYMENTS
#--------------------------------

class PaymentInstrument(str, Enum):
    LC = "LC"
    ADV = "Adv"
    DP = "DP"
    CAD = "CAD"


class PaymentStatus(str, Enum):
    PAID = "Paid"
    UNPAID = "Unpaid"


#--------------------------------
# WHERE THE DEMAND FOR A LINE CAME FROM
#--------------------------------

class RequisitionType(str, Enum):
    STORE = "Store"
    ENGINEERING = "Engineering"
    OTHERS = "Others"


#--------------------------------
# WHAT A CHANGE HISTORY ROW RECORDS
#--------------------------------

class ChangeType(str, Enum):
    UPDATE = "Update"
    DELETE = "Delete"


#--------------------------------
# WHAT AN ACTIVITY LOG ROW RECORDS
#--------------------------------

class LogAction(str, Enum):
    LOGIN = "Login"
    LOGOUT = "Logout"
    CREATE = "Create"
    UPDATE = "Update"
    DELETE = "Delete"
    STATUS_CHANGE = "Status change"
    ETA_REVISION = "ETA revision"
    VERIFY = "Verify"
    REVERT = "Revert"
    RESTORE = "Restore"


#--------------------------------
# LOGISTICS: EXPORT OR LOCAL ORDER
#
# The order type drives which fields apply on several
# steps, which is why it sits on the order itself.
#--------------------------------

class OrderType(str, Enum):
    EXPORT = "Export"
    LOCAL = "Local"


#--------------------------------
# LOGISTICS: DEPARTMENT
#
# Sits on the order header and drives the merged "Order Type"
# label in the list (e.g. "Cement Export", "General Local").
#--------------------------------

class Department(str, Enum):
    CEMENT = "Cement"
    SUGAR = "Sugar"
    GENERAL = "General"


#--------------------------------
# INCOTERM
#
# Shared by imports and logistics. Kept short: only the terms that
# actually change who arranges freight, not the full ICC list. FOB
# feeds the trucking module's import-FOB request derivation.
#--------------------------------

class Incoterm(str, Enum):
    FOB = "FOB"
    CIF = "CIF"
    CFR = "CFR"
    EXW = "EXW"
    DAP = "DAP"


#--------------------------------
# LOGISTICS: PACKING STATUS
#
# Each package advances on its own through these stages. Separate
# from the order-level LogisticsStatus below.
#--------------------------------

class PackingStatus(str, Enum):
    PACKING_UNDER_MANUFACTURING = "Packing under manufacturing"
    UNDER_PACKING = "Under Packing"
    UNDER_PAINT = "Under Paint"
    UNDER_FINAL_PACKING = "Under Final Packing"
    PACKED = "Packed"


#--------------------------------
# LOGISTICS: THE STAGES AN ORDER MOVES THROUGH
#
# One list holding both the export and local stages.
# Export orders run the full chain; local orders skip the
# sea legs and close at Delivered. The order here is the
# order they actually happen in.
#--------------------------------

class LogisticsStatus(str, Enum):
    UNDER_PRODUCTION = "Under Production"
    UNDER_PACKING = "Under Packing"
    TRANSPORTATION = "Transportation"
    UNDER_SHIPPING_ARRANGEMENT = "Under Shipping Arrangement"
    AT_QFL = "At QFL"
    AT_PORT = "At Port"
    ON_WATER = "On Water"
    DELIVERED = "Delivered"


#--------------------------------
# TRUCKING: WHICH WAY THE GOODS MOVE
#
# The movement type drives which fields apply on several
# steps, which is why it sits on the consignment.
#--------------------------------

class MovementType(str, Enum):
    INTRAFACTORY = "Intrafactory"
    OUTBOUND = "Outbound"
    INBOUND = "Inbound"


#--------------------------------
# TRUCKING: WHERE A JOB CAME FROM
#
# A derived row reflects a live logistics or import record;
# a manual row is fully owned by the trucking operator.
#--------------------------------

class TruckingSource(str, Enum):
    MANUAL = "manual"
    FROM_LOGISTICS = "from-logistics"
    FROM_IMPORT_FOB = "from-import-fob"
    FROM_EXPORT = "from-export"


#--------------------------------
# TRUCKING: KIND OF SHIFTING
#--------------------------------

class ShiftingType(str, Enum):
    REGULAR = "Regular"
    SPECIAL = "Special"
    OTHERS = "Others"


#--------------------------------
# TRUCKING: CONTAINER SIZE (INBOUND / IMPORT FOB)
#--------------------------------

class ContainerType(str, Enum):
    TWENTY_FT = "20ft"
    FORTY_FT = "40ft"
    FORTY_FT_HC = "40ft HC"
    OTHER = "Other"


#--------------------------------
# TRUCKING: WHO SETTLES THE FREIGHT
#--------------------------------

class TruckingPaymentStatus(str, Enum):
    CUSTOMER_TO_PAY = "Customer to pay"
    QG_TO_PAY = "QG to pay"


#--------------------------------
# TRUCKING: PER VEHICLE TRACKING PIPELINE
#
# Each truck advances on its own. The consignment level
# status is a rollup over the vehicles, worked out on the
# front end, never stored. Order matters, it is the order
# the stages actually happen in.
#--------------------------------

class VehicleTrackingStatus(str, Enum):
    GOING_TO_LOAD = "Going to load"
    LOADING = "Loading"
    ON_ROAD = "On road"
    DELIVERED = "Delivered"


#--------------------------------
# LOGISTICS: SHIPMENT MODE
#
# EFS = Export Facilitation Scheme (duty-suspended inputs for export
# manufacturing); Regular = standard duty-paid. An attribute the Logistics
# team sets on the order itself, like department — not something derived
# from the goods.
#--------------------------------

class ShipmentMode(str, Enum):
    EFS = "EFS"
    REGULAR = "Regular"


#--------------------------------
# LOGISTICS: WHAT KIND OF JOB THE ORDER IS
#
# A customer-rework job (a customer sends used goods in to be reworked) needs
# exactly the same shape as an export/local order — items, packing, shipping,
# expenditures, status, Send to Trucking — so it lives in the SAME table
# rather than getting one of its own. This column is the discriminator: the
# Orders list shows 'standard', the Service Jobs tab shows 'rework'.
#
# NOT a user-facing choice. There is no form control for it: it follows from
# which flow was entered ("New Logistics Order" vs "New Rework Job"), is set
# once at creation, and is IMMUTABLE afterwards — the update route ignores it,
# so a PUT can never move a record between the two tabs.
#
# Imports is not involved in a rework job. The other half of Service Jobs
# (import-FOB) is NOT a row here at all — it is derived from the imports
# consignments bought FOB (see cross_module.py), so it needs no job kind.
#--------------------------------

class JobKind(str, Enum):
    STANDARD = "standard"
    REWORK = "rework"


#--------------------------------
# STOCK: ABC RANK
#
# The ABC classification of a stocked item. A and B come from the "AB Items"
# workbook, which ranks per BRANCH — the same item can be an A line at one
# branch and a B line at another, because the ranking is driven by that
# branch's own stock and issuance. That is why the rank lives on `stock`
# (item + branch) and not on the `items` master, which has no branch.
#
# C is the default rather than a value anyone records: the workbook only
# lists A and B items, so anything it does not mention is a C line.
#--------------------------------

class ItemRank(str, Enum):
    A = "A"
    B = "B"
    C = "C"