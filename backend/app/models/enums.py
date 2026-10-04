import enum

class UserRole(str, enum.Enum):
    FARMER = "FARMER"
    EXTENSION_OFFICER = "EXTENSION_OFFICER"
    ADMIN = "ADMIN"

class IrrigationSource(str, enum.Enum):
    RAINFED = "RAINFED"
    CANAL = "CANAL"
    BOREWELL_WELL = "BOREWELL_WELL"
    TANK_POND = "TANK_POND"
    DRIP_SPRINKLER = "DRIP_SPRINKLER"
    OTHER = "OTHER"

class CropStage(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    SOWN = "SOWN"
    VEGETATIVE = "VEGETATIVE"
    FLOWERING_PODDING = "FLOWERING_PODDING"
    HARVEST_READY = "HARVEST_READY"

class DataSource(str, enum.Enum):
    LIVE = "LIVE"
    HINDCAST = "HINDCAST"
    SIMULATED = "SIMULATED"

class AdvisorySeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    # Aliases
    INFO = "INFO"
    ADVISORY = "ADVISORY"

class AdvisoryApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"

class NotificationChannel(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    PUSH = "PUSH"

class NotificationStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BLOCKED_SIMULATED = "BLOCKED_SIMULATED"
    BLOCKED_NON_LIVE = "BLOCKED_NON_LIVE"
    BLOCKED_CONSENT = "BLOCKED_CONSENT"
    BLOCKED_OPT_OUT = "BLOCKED_OPT_OUT"
