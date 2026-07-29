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
# ROLES
#--------------------------------

class Role(str, Enum):
    ADMIN="admin"
    VIEWER="viewer"
    MANAGER="manager"
    ENTRY_OPERATOR="entry operator"


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
    TT_LC_IN_PROCESS = "TT/LC in process"
    UNDER_PRODUCTION = "Under production"
    READY_AWAITING_SAILING = "Ready awaiting sailing"
    IN_TRANSIT = "In transit"
    ARRIVED_AT_PORT = "Arrived at port"
    UNDER_CUSTOM_CLEARANCE = "Under custom clearance"
    UNDER_EXAMINATION = "Under examination"
    UNDER_ASSESSMENT = "Under assessment"
    ARRIVED_AT_QFL = "Arrived at QFL"
    ON_ROAD = "On road"
    ARRIVED_AT_WORKS = "Arrived at works"


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
# TRUCKING: WHETHER A BUILTY WAS ISSUED
#--------------------------------

class BuiltyStatus(str, Enum):
    YES = "Yes"
    NA = "NA"