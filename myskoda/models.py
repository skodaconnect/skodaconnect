"""Models, Types, Enums, ..."""

from enum import auto, StrEnum


class Capability(StrEnum):
    """All posible capabilities as returned by api/v2/garage/vehicles/VIN"""

    @staticmethod
    def _generate_next_value_(name, *args):
        """Force auto values to be uppercase."""
        return name.upper()

    AIR_CONDITIONING = auto()
    AIR_CONDITIONING_SAVE_AND_ACTIVATE = auto()
    AIR_CONDITIONING_SMART_SETTINGS = auto()
    AIR_CONDITIONING_TIMERS = auto()
    AUTOMATION = auto()
    BATTERY_CHARGING_CARE = auto()
    BATTERY_SUPPORT = auto()
    CHARGE_MODE_SELECTION = auto()
    CHARGING = auto()
    CHARGING_MEB = auto()
    CHARGING_PROFILES = auto()
    CHARGING_STATIONS = auto()
    CUBIC = auto()
    DCS = auto()
    DESTINATION_IMPORT_UPGRADABLE = auto()
    DESTINATIONS = auto()
    DIGICERT = auto()
    EV_RANGE = auto()
    EV_ROUTE_PLANNING = auto()
    EXTENDED_CHARGING_SETTINGS = auto()
    GUEST_USER_MANAGEMENT = auto()
    MAP_UPDATE = auto()
    MEASUREMENTS = auto()
    ONLINE_SPEECH_GPS = auto()
    PARKING_INFORMATION = auto()
    PARKING_POSITION = auto()
    PAY_TO_PARK = auto()
    POI_SEARCH = auto()
    POWERPASS_TARIFFS = auto()
    ROADSIDE_ASSISTANT = auto()
    ROUTE_PLANNING_5_CHARGERS = auto()
    ROUTING = auto()
    SERVICE_PARTNER = auto()
    SMART_PARKING = auto()
    STATE = auto()
    SUBSCRIPTIONS = auto()
    TRAFFIC_INFORMATION = auto()
    VEHICLE_HEALTH_INSPECTION = auto()
    VEHICLE_HEALTH_WARNINGS = auto()
    VEHICLE_SERVICES_BACKUPS = auto()
    VEHICLE_WAKE_UP_TRIGGER = auto()
    WARNING_LIGHTS = auto()
    WEB_RADIO = auto()
    WINDOW_HEATING = auto()
