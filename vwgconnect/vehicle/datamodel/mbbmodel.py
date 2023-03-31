"""
skodaconnect - A Python 3 library for interacting with Skoda Connect.

For more details and documentation, visit the github page at:
    https://github.com/skodaconnect/skodaconnect

This models the different MBB API Endpoints into parseable objects.
"""


class MBBDataModel:
    """Base Data Model for representing API data."""

    def __init__(self, data: dict = None):
        """Init class."""
        self._data = {}
        if type(data) is dict:
            self.data = data.copy()

    @property
    def data(self):
        """Returns operationlist data."""
        return self._data

    @data.setter
    def data(self, data: dict):
        """Update object data."""
        # Do nothing if provided data is not dict
        if type(data) is dict:
            self._data.update(data)


class MBBHomeRegion(MBBDataModel):
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Set initial URI values."""
        super.__init__(data)
        uri = self._data.get("homeRegion", {}).get("baseUri", {}).get("content", None)
        if uri == "https://mal-3a.prd.eu.dp.vwg-connect.com/api":
            self.base_uri = uri.split("/api")[0].replace("mal-", "fal-")
        else:
            self.base_uri = "https://msg.volkswagen.de"
        self.auth_uri = uri.split("/api")[0]

    @property
    def auth_uri(self):
        """Returns the URI for auth actions."""
        return self.auth_uri

    @property
    def base_uri(self):
        """Returns the base URI for get actions."""
        return self.base_uri


class MBBOperationList:
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        self._data = {}
        if type(data) is dict:
            self.data = data.copy()

    @property
    def data(self):
        """Returns operationlist data."""
        return self._data

    @data.setter
    def data(self, data: dict):
        """Parse the operationlist into somwhat legible data dict."""
        try:
            parsed = {}
            service_list = data.get("operationList", {}).get("serviceInfo", [])
            for svc_obj in service_list:
                # Iterate and add all services we can interact with
                if svc_obj.get("invocationUrl", False):
                    parsed.update({svc_obj.pop("serviceId", None): svc_obj})
            self._data.update(parsed)
        except:
            pass


class MBBCharger(MBBDataModel):
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        super.__init__(data)

    @property
    def max_charge_current(self):
        """Charger maximum current."""
        return (
            self._data.get("charger", {})
            .get("settings", {})
            .get("maxChargeCurrent", {})
            .get("content", None)
        )

    @property
    def mode(self):
        """Charging mode selection."""
        return (
            self._data.get("charger", {})
            .get("settings", {})
            .get("chargeModeSelection", {})
            .get("value", {})
            .get("content", None)
        )

    @property
    def remaining_charging_time(self):
        """Time remaining until charged."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("batteryStatusData", {})
            .get("remainingChargingTime", {})
            .get("content", None)
        )

    @property
    def remaining_charging_time_target_soc(self):
        """Time remaining until charged to target state of charge."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("batteryStatusData", {})
            .get("remainingChargingTimeTargetSOC", {})
            .get("content", None)
        )

    @property
    def state_of_charge(self):
        """State of charge."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("batteryStatusData", {})
            .get("stateOfCharge", {})
            .get("content", None)
        )

    @property
    def charging_mode(self):
        """Charging mode."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("chargingStatusData", {})
            .get("chargingMode", {})
            .get("content", None)
        )

    @property
    def charging_reason(self):
        """Charging reason."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("chargingStatusData", {})
            .get("chargingReason", {})
            .get("content", None)
        )

    @property
    def charging_state(self):
        """Charging state."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("chargingStatusData", {})
            .get("chargingState", {})
            .get("content", None)
        )

    @property
    def charging_error_code(self):
        """Charging state error code."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("chargingStatusData", {})
            .get("chargingStateErrorCode", {})
            .get("content", None)
        )

    @property
    def energy_flow(self):
        """Energy flow."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("chargingStatusData", {})
            .get("energyFlow", {})
            .get("content", None)
        )

    @property
    def external_power(self):
        """External power supply state."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("chargingStatusData", {})
            .get("externalPowerSupplyState", {})
            .get("content", None)
        )

    @property
    def primary_engine(self):
        """Primary enginge type."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("cruisingRangeStatusData", {})
            .get("engineTypeFirstEngine", {})
            .get("content", None)
        )

    @property
    def secondary_engine(self):
        """Secondary enginge type."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("cruisingRangeStatusData", {})
            .get("engineTypeSecondEngine", {})
            .get("content", None)
        )

    @property
    def primary_engine_range(self):
        """Primary enginge range."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("cruisingRangeStatusData", {})
            .get("primaryEngineRange", {})
            .get("content", None)
        )

    @property
    def secondary_engine_range(self):
        """Secondary enginge range."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("cruisingRangeStatusData", {})
            .get("secondaryEngineRange", {})
            .get("content", None)
        )

    @property
    def led_state(self):
        """State of charging LED."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("ledStatusData", {})
            .get("ledState", {})
            .get("content", None)
        )

    @property
    def led_color(self):
        """Color of charging LED."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("ledStatusData", {})
            .get("ledColor", {})
            .get("content", None)
        )

    @property
    def plug_state(self):
        """Status of charging plug."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("plugStatusData", {})
            .get("plugState", {})
            .get("content", None)
        )

    @property
    def plug_locked(self):
        """Status of charging plug lock."""
        return (
            self._data.get("charger", {})
            .get("status", {})
            .get("plugStatusData", {})
            .get("lockState", {})
            .get("content", None)
        )


class MBBClimater(MBBDataModel):
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        super.__init__(data)

    @property
    def climatisation_on_battery(self):
        """Climatisation with battery power."""
        return (
            self._data.get("climater", {})
            .get("settings", {})
            .get("climatisationWithoutHVpower", {})
            .get("content", None)
        )

    @property
    def heater_source(self):
        """Heater source for climatisation."""
        return (
            self._data.get("climater", {})
            .get("settings", {})
            .get("heaterSource", {})
            .get("content", None)
        )

    @property
    def target_temp(self):
        """Climatisation target temp."""
        return (
            self._data.get("climater", {})
            .get("settings", {})
            .get("targetTemperature", {})
            .get("content", None)
        )

    @property
    def climatisation_reason(self):
        """Climatisation start reason."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("climatisationStatusData", {})
            .get("climatisationReason", {})
            .get("content", None)
        )

    @property
    def climatisation_state(self):
        """Climatisation state."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("climatisationStatusData", {})
            .get("climatisationState", {})
            .get("content", None)
        )

    @property
    def climatisation_error(self):
        """Climatisation error code."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("climatisationStatusData", {})
            .get("climatisationStateErrorCode", {})
            .get("content", None)
        )

    @property
    def climatisation_time_remaining(self):
        """Remaining climatisation time."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("climatisationStatusData", {})
            .get("remainingClimatisationTime", {})
            .get("content", None)
        )

    @property
    def outside_temp(self):
        """Outside temperature."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("temperatureStatusData", {})
            .get("outdoorTemperature", {})
            .get("content", None)
        )

    @property
    def parked_timestamp(self):
        """Timestamp when vehicle was parked."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("vehicleParkingClockStatusData", {})
            .get("vehicleParkingClock", {})
            .get("content", None)
        )

    @property
    def window_heating_error(self):
        """Window heating error code."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("windowHeatingStatusData", {})
            .get("windowHeatingErrorCode", {})
            .get("content", None)
        )

    @property
    def window_heating_front(self):
        """Window heating status front."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("windowHeatingStatusData", {})
            .get("windowHeatingStateFront", {})
            .get("content", None)
        )

    @property
    def window_heating_rear(self):
        """Window heating status rear."""
        return (
            self._data.get("climater", {})
            .get("status", {})
            .get("windowHeatingStatusData", {})
            .get("windowHeatingStateRear", {})
            .get("content", None)
        )


class MBBStatus:
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        self._data = {}
        if type(data) is dict:
            self.data = data.copy()

    @property
    def data(self):
        """Returns operationlist data."""
        return self._data

    @data.setter
    def data(self, data: dict):
        """Parse the StoredVehicleDataResponse and store as manageable dict."""
        try:
            parsed = dict(
                [
                    (e["id"], e if "value" in e else "")
                    for f in [
                        s["field"] for s in data["StoredVehicleDataResponse"]["vehicleData"]["data"]
                    ]
                    for e in f
                ]
            )
            self._data.update(parsed)
        except:
            pass

    @property
    def last_connected(self) -> str:
        """UTC timestamp when last connected."""
        return self._data.get("0x0101010001", {}).get("tsTssReceivedUtc", None)

    @property
    def odometer(self) -> int:
        """Odometer value."""
        return self._data.get("0x0101010002", {}).get("value", None)

    @property
    def oil_inspection_distance(self) -> tuple:
        """Distance until next oil inspection."""
        return (
            self._data.get("0x0203010001", {}).get("value", None),
            self._data.get("0x0203010001", {}).get("unit", None),
        )

    @property
    def oil_inspection_time(self) -> int:
        """Time until next oil inspection."""
        return self._data.get("0x0203010002", {}).get("value", None)

    @property
    def inspection_distance(self) -> tuple:
        """Distance until next inspection."""
        return (
            self._data.get("0x0203010003", {}).get("value", None),
            self._data.get("0x0203010003", {}).get("unit", None),
        )

    @property
    def inspection_time(self) -> int:
        """Time until next inspection."""
        return self._data.get("0x0203010004", {}).get("value", None)

    @property
    def oil_inspection_warning(self):
        """Oil Inspection warning."""
        return self._data.get("0x0203010005", {}).get("value", None)

    @property
    def inspection_alarm(self):
        """Inspection alarm."""
        return self._data.get("0x0203010006", {}).get("value", None)

    @property
    def inspection_monthly_mileage(self) -> int:
        """Time until next inspection."""
        return self._data.get("0x0203010007", {}).get("value", None)

    @property
    def oil_level_amount(self) -> tuple:
        """Oil level amount in liter."""
        return (
            self._data.get("0x0204040001", {}).get("value", None),
            self._data.get("0x0204040001", {}).get("unit", None),
        )

    @property
    def oil_level_warning(self) -> tuple:
        """Oil level minimum warning."""
        return (
            self._data.get("0x0204040002", {}).get("value", None),
            self._data.get("0x0204040002", {}).get("unit", None),
        )

    @property
    def oil_level(self) -> tuple:
        """Oil level in percent."""
        return (
            self._data.get("0x0204040003", {}).get("value", None),
            self._data.get("0x0204040003", {}).get("unit", None),
        )

    @property
    def oil_level2(self) -> tuple:
        """Oil level 2 in percent."""
        return (
            self._data.get("0x0204040006", {}).get("value", None),
            self._data.get("0x0204040006", {}).get("unit", None),
        )

    @property
    def ad_blue_range(self) -> tuple:
        """Range of AD-blue."""
        return (
            self._data.get("0x02040C0001", {}).get("value", None),
            self._data.get("0x02040C0001", {}).get("unit", None),
        )

    @property
    def oil_level(self) -> tuple:
        """Oil level in percent."""
        return (
            self._data.get("0x0204040003", {}).get("value", None),
            self._data.get("0x0204040003", {}).get("unit", None),
        )

    @property
    def parking_brake(self) -> tuple:
        """Parking brake state."""
        return (
            self._data.get("0x0301030001", {}).get("value", None),
            self._data.get("0x0301030001", {}).get("textId", None),
        )

    @property
    def state_of_charge(self) -> tuple:
        """Battery charge percentage."""
        return (
            self._data.get("0x0301030002", {}).get("value", None),
            self._data.get("0x0301030002", {}).get("unit", None),
        )

    @property
    def bem(self) -> tuple:
        """BEM?."""
        return (
            self._data.get("0x0301030003", {}).get("value", None),
            self._data.get("0x0301030003", {}).get("unit", None),
        )

    @property
    def primary_range(self) -> tuple:
        """Range of primary drive."""
        return (
            self._data.get("0x0301030006", {}).get("value", None),
            self._data.get("0x0301030006", {}).get("unit", None),
        )

    @property
    def primary_drive(self) -> tuple:
        """Primary engine type."""
        return (
            self._data.get("0x0301030007", {}).get("value", None),
            self._data.get("0x0301030007", {}).get("textId", None),
        )

    @property
    def secondary_range(self) -> tuple:
        """Range of secondary drive."""
        return (
            self._data.get("0x0301030008", {}).get("value", None),
            self._data.get("0x0301030008", {}).get("unit", None),
        )

    @property
    def primary_drive(self) -> tuple:
        """Secondary engine type."""
        return (
            self._data.get("0x0301030009", {}).get("value", None),
            self._data.get("0x0301030009", {}).get("textId", None),
        )

    @property
    def fuel_level(self) -> tuple:
        """Fuel level in percentage."""
        return (
            self._data.get("0x030103000A", {}).get("value", None),
            self._data.get("0x030103000A", {}).get("unit", None),
        )

    @property
    def cng_level(self) -> tuple:
        """Gas level in percentage."""
        return (
            self._data.get("0x030103000D", {}).get("value", None),
            self._data.get("0x030103000D", {}).get("unit", None),
        )

    @property
    def door_left_front_locked(self) -> tuple:
        """State of left front door lock."""
        return (
            self._data.get("0x0301040001", {}).get("value", None),
            self._data.get("0x0301040001", {}).get("textId", None),
        )

    @property
    def door_left_front(self) -> tuple:
        """State of left front door open."""
        return (
            self._data.get("0x0301040002", {}).get("value", None),
            self._data.get("0x0301040002", {}).get("textId", None),
        )

    @property
    def door_left_front_safety(self) -> tuple:
        """State of left front door safety."""
        return (
            self._data.get("0x0301040003", {}).get("value", None),
            self._data.get("0x0301040003", {}).get("textId", None),
        )

    @property
    def door_left_rear_locked(self) -> tuple:
        """State of left rear door lock."""
        return (
            self._data.get("0x0301040004", {}).get("value", None),
            self._data.get("0x0301040004", {}).get("textId", None),
        )

    @property
    def door_left_rear(self) -> tuple:
        """State of left rear door open."""
        return (
            self._data.get("0x0301040005", {}).get("value", None),
            self._data.get("0x0301040005", {}).get("textId", None),
        )

    @property
    def door_left_rear_safety(self) -> tuple:
        """State of left rear door safety."""
        return (
            self._data.get("0x0301040006", {}).get("value", None),
            self._data.get("0x0301040006", {}).get("textId", None),
        )

    @property
    def door_right_front_locked(self) -> tuple:
        """State of right front door lock."""
        return (
            self._data.get("0x0301040007", {}).get("value", None),
            self._data.get("0x0301040007", {}).get("textId", None),
        )

    @property
    def door_right_front(self) -> tuple:
        """State of right front door open."""
        return (
            self._data.get("0x0301040008", {}).get("value", None),
            self._data.get("0x0301040008", {}).get("textId", None),
        )

    @property
    def door_right_front_safety(self) -> tuple:
        """State of right front door safety."""
        return (
            self._data.get("0x0301040009", {}).get("value", None),
            self._data.get("0x0301040009", {}).get("textId", None),
        )

    @property
    def door_right_rear_locked(self) -> tuple:
        """State of right rear door lock."""
        return (
            self._data.get("0x030104000A", {}).get("value", None),
            self._data.get("0x030104000A", {}).get("textId", None),
        )

    @property
    def door_right_rear(self) -> tuple:
        """State of right rear door open."""
        return (
            self._data.get("0x030104000B", {}).get("value", None),
            self._data.get("0x030104000B", {}).get("textId", None),
        )

    @property
    def door_right_rear_safety(self) -> tuple:
        """State of right rear door safety."""
        return (
            self._data.get("0x030104000C", {}).get("value", None),
            self._data.get("0x030104000C", {}).get("textId", None),
        )

    @property
    def trunk_locked(self) -> tuple:
        """State of trunk lock."""
        return (
            self._data.get("0x030104000D", {}).get("value", None),
            self._data.get("0x030104000D", {}).get("textId", None),
        )

    @property
    def trunk(self) -> tuple:
        """State of trunk open."""
        return (
            self._data.get("0x030104000E", {}).get("value", None),
            self._data.get("0x030104000E", {}).get("textId", None),
        )

    @property
    def trunk_safety(self) -> tuple:
        """State of trunk safety."""
        return (
            self._data.get("0x030104000F", {}).get("value", None),
            self._data.get("0x030104000F", {}).get("textId", None),
        )

    @property
    def hood_locked(self) -> tuple:
        """State of hood lock."""
        return (
            self._data.get("0x0301040010", {}).get("value", None),
            self._data.get("0x0301040010", {}).get("textId", None),
        )

    @property
    def hood(self) -> tuple:
        """State of hood open."""
        return (
            self._data.get("0x0301040011", {}).get("value", None),
            self._data.get("0x0301040011", {}).get("textId", None),
        )

    @property
    def hood_safety(self) -> tuple:
        """State of hood safety."""
        return (
            self._data.get("0x0301040012", {}).get("value", None),
            self._data.get("0x0301040012", {}).get("textId", None),
        )

    @property
    def window_left_front(self) -> tuple:
        """State of left front window."""
        return (
            self._data.get("0x0301050001", {}).get("value", None),
            self._data.get("0x0301050001", {}).get("textId", None),
        )

    @property
    def window_left_front_position(self) -> tuple:
        """Left front window position."""
        return (
            self._data.get("0x0301050002", {}).get("value", None),
            self._data.get("0x0301050002", {}).get("textId", None),
        )

    @property
    def window_left_rear(self) -> tuple:
        """State of left rear window."""
        return (
            self._data.get("0x0301050003", {}).get("value", None),
            self._data.get("0x0301050003", {}).get("textId", None),
        )

    @property
    def window_left_rear_position(self) -> tuple:
        """Left rear window position."""
        return (
            self._data.get("0x0301050004", {}).get("value", None),
            self._data.get("0x0301050004", {}).get("textId", None),
        )

    @property
    def window_right_front(self) -> tuple:
        """State of right front window."""
        return (
            self._data.get("0x0301050005", {}).get("value", None),
            self._data.get("0x0301050005", {}).get("textId", None),
        )

    @property
    def window_right_front_position(self) -> tuple:
        """Right front window position."""
        return (
            self._data.get("0x0301050006", {}).get("value", None),
            self._data.get("0x0301050006", {}).get("textId", None),
        )

    @property
    def window_right_rear(self) -> tuple:
        """State of right rear window."""
        return (
            self._data.get("0x0301050007", {}).get("value", None),
            self._data.get("0x0301050007", {}).get("textId", None),
        )

    @property
    def window_right_rear_position(self) -> tuple:
        """Right rear window position."""
        return (
            self._data.get("0x0301050008", {}).get("value", None),
            self._data.get("0x0301050008", {}).get("textId", None),
        )

    @property
    def convertible_top(self) -> tuple:
        """State of convertible top."""
        return (
            self._data.get("0x0301050009", {}).get("value", None),
            self._data.get("0x0301050009", {}).get("textId", None),
        )

    @property
    def convertible_top_position(self) -> tuple:
        """Convertible top position."""
        return (
            self._data.get("0x030105000A", {}).get("value", None),
            self._data.get("0x030105000A", {}).get("textId", None),
        )

    @property
    def sun_roof_motor_cover(self) -> tuple:
        """State of sun roof motor cover."""
        return (
            self._data.get("0x030105000B", {}).get("value", None),
            self._data.get("0x030105000B", {}).get("textId", None),
        )

    @property
    def sun_roof_motor_cover_position(self) -> tuple:
        """Sun roof motor cover position."""
        return (
            self._data.get("0x030105000C", {}).get("value", None),
            self._data.get("0x030105000C", {}).get("textId", None),
        )

    @property
    def sun_roof_rear_motor_cover(self) -> tuple:
        """State of rear sun roof motor cover."""
        return (
            self._data.get("0x030105000D", {}).get("value", None),
            self._data.get("0x030105000D", {}).get("textId", None),
        )

    @property
    def sun_roof_rear_motor_cover_position(self) -> tuple:
        """Sun roof rear motor cover position."""
        return (
            self._data.get("0x030105000E", {}).get("value", None),
            self._data.get("0x030105000E", {}).get("textId", None),
        )

    @property
    def service_flap(self) -> tuple:
        """State of service flap."""
        return (
            self._data.get("0x030105000F", {}).get("value", None),
            self._data.get("0x030105000F", {}).get("textId", None),
        )

    @property
    def service_flap_position(self) -> tuple:
        """Service flap position."""
        return (
            self._data.get("0x0301050010", {}).get("value", None),
            self._data.get("0x0301050010", {}).get("textId", None),
        )

    @property
    def spoiler(self) -> tuple:
        """State of spoiler."""
        return (
            self._data.get("0x0301050011", {}).get("value", None),
            self._data.get("0x0301050011", {}).get("textId", None),
        )

    @property
    def spoiler_position(self) -> tuple:
        """Spoiler position."""
        return (
            self._data.get("0x0301050012", {}).get("value", None),
            self._data.get("0x0301050012", {}).get("textId", None),
        )

    @property
    def tps_left_front(self) -> tuple:
        """Tyre pressure sensor left front."""
        return (
            self._data.get("0x0301060001", {}).get("value", None),
            self._data.get("0x0301060001", {}).get("textId", None),
        )

    @property
    def tps_left_front_desired(self) -> tuple:
        """Tyre pressure sensor left front desired value."""
        return (
            self._data.get("0x0301060002", {}).get("value", None),
            self._data.get("0x0301060002", {}).get("textId", None),
        )

    @property
    def tps_left_rear(self) -> tuple:
        """Tyre pressure sensor left rear."""
        return (
            self._data.get("0x0301060003", {}).get("value", None),
            self._data.get("0x0301060003", {}).get("textId", None),
        )

    @property
    def tps_left_rear_desired(self) -> tuple:
        """Tyre pressure sensor left rear desired value."""
        return (
            self._data.get("0x0301060004", {}).get("value", None),
            self._data.get("0x0301060004", {}).get("textId", None),
        )

    @property
    def tps_right_front(self) -> tuple:
        """Tyre pressure sensor right front."""
        return (
            self._data.get("0x0301060005", {}).get("value", None),
            self._data.get("0x0301060005", {}).get("textId", None),
        )

    @property
    def tps_right_front_desired(self) -> tuple:
        """Tyre pressure sensor right front desired value."""
        return (
            self._data.get("0x0301060006", {}).get("value", None),
            self._data.get("0x0301060006", {}).get("textId", None),
        )

    @property
    def tps_right_rear(self) -> tuple:
        """Tyre pressure sensor right rear."""
        return (
            self._data.get("0x0301060007", {}).get("value", None),
            self._data.get("0x0301060007", {}).get("textId", None),
        )

    @property
    def tps_right_rear_desired(self) -> tuple:
        """Tyre pressure sensor right rear desired value."""
        return (
            self._data.get("0x0301060008", {}).get("value", None),
            self._data.get("0x0301060008", {}).get("textId", None),
        )

    @property
    def tps_spare(self) -> tuple:
        """Tyre pressure sensor spare."""
        return (
            self._data.get("0x0301060009", {}).get("value", None),
            self._data.get("0x0301060009", {}).get("textId", None),
        )

    @property
    def tps_spare_desired(self) -> tuple:
        """Tyre pressure sensor spare desired value."""
        return (
            self._data.get("0x030106000A", {}).get("value", None),
            self._data.get("0x030106000A", {}).get("textId", None),
        )

    @property
    def tps_left_front_diff(self) -> tuple:
        """TPS left front pressure difference."""
        return (
            self._data.get("0x030106000B", {}).get("value", None),
            self._data.get("0x030106000B", {}).get("textId", None),
        )

    @property
    def tps_left_rear_diff(self) -> tuple:
        """TPS left rear pressure difference."""
        return (
            self._data.get("0x030106000C", {}).get("value", None),
            self._data.get("0x030106000C", {}).get("textId", None),
        )

    @property
    def tps_right_front_diff(self) -> tuple:
        """TPS right front pressure difference."""
        return (
            self._data.get("0x030106000D", {}).get("value", None),
            self._data.get("0x030106000D", {}).get("textId", None),
        )

    @property
    def tps_right_rear_diff(self) -> tuple:
        """TPS right_rear pressure difference."""
        return (
            self._data.get("0x030106000E", {}).get("value", None),
            self._data.get("0x030106000E", {}).get("textId", None),
        )

    @property
    def tps_spare_diff(self) -> tuple:
        """TPS spare pressure difference."""
        return (
            self._data.get("0x030106000F", {}).get("value", None),
            self._data.get("0x030106000F", {}).get("textId", None),
        )


class MBBTrip:
    """
    Data model class representing the MBB API endpoints structure.
    """

    def __init__(self, data: dict = None):
        """Init class."""
        self._data = {}
        if type(data) is dict:
            self.data = data.copy()

    @property
    def data(self):
        """Returns trip statistics data."""
        return self._data

    @data.setter
    def data(self, data: dict):
        """Parse the trip statistics response and store as manageable dict."""
        try:
            if type(data.get("tripDataList", {}).get("tripData")) is not list:
                # Latest entry
                trip_data = data.get("tripDataList", {}).get("tripData")
            else:
                # Get last element in list = latest entry
                trip_data = data.get("tripDataList", {}).get("tripData")[-1:][0]

            trip_type = trip_data.pop("tripType")
            self._data.update(dict({trip_type: trip_data}))
        except:
            pass

    @property
    def cyclic_auxiliary_consumption(self):
        """Average auxiliary consumption since refueling."""
        return self._data.get("cyclic", {}).get("averageAuxConsumerConsumption", None)

    @property
    def cyclic_electric_consumption(self):
        """Average electric enginge consumption since refueling."""
        return self._data.get("cyclic", {}).get("averageElectricEngineConsumption", None)

    @property
    def cyclic_fuel_consumption(self):
        """Average fuel consumption since refueling."""
        return self._data.get("cyclic", {}).get("averageFuelConsumption", None)

    @property
    def cyclic_recuperation(self):
        """Average fuel consumption since refueling."""
        return self._data.get("cyclic", {}).get("averageRecuperation", None)

    @property
    def cyclic_average_speed(self):
        """Average speed since refueling."""
        return self._data.get("cyclic", {}).get("averageSpeed", None)

    @property
    def cyclic_distance(self):
        """Distance since last refuel."""
        return self._data.get("cyclic", {}).get("mileage", None)

    @property
    def cyclic_start_mileage(self):
        """Odometer at last refuel."""
        return self._data.get("cyclic", {}).get("startMileage", None)

    @property
    def cyclic_time_traveled(self):
        """Time traveled since last refuel."""
        return self._data.get("cyclic", {}).get("traveltime", None)

    @property
    def last_auxiliary_consumption(self):
        """Average auxiliary consumption of last trip."""
        return self._data.get("shortTerm", {}).get("averageAuxConsumerConsumption", None)

    @property
    def last_electric_consumption(self):
        """Average electric enginge consumption of last trip."""
        return self._data.get("shortTerm", {}).get("averageElectricEngineConsumption", None)

    @property
    def last_fuel_consumption(self):
        """Average fuel consumption of last trip."""
        return self._data.get("shortTerm", {}).get("averageFuelConsumption", None)

    @property
    def last_recuperation(self):
        """Average fuel consumption of last trip."""
        return self._data.get("shortTerm", {}).get("averageRecuperation", None)

    @property
    def last_average_speed(self):
        """Average speed of last trip.."""
        return self._data.get("shortTerm", {}).get("averageSpeed", None)

    @property
    def last_distance(self):
        """Distance of last trip."""
        return self._data.get("shortTerm", {}).get("mileage", None)

    @property
    def last_start_mileage(self):
        """Odometer at start of last trip."""
        return self._data.get("shortTerm", {}).get("startMileage", None)

    @property
    def last_time_traveled(self):
        """Time traveled last trip."""
        return self._data.get("shortTerm", {}).get("traveltime", None)

    @property
    def longterm_auxiliary_consumption(self):
        """Long term average auxiliary consumption."""
        return self._data.get("longTerm", {}).get("averageAuxConsumerConsumption", None)

    @property
    def longterm_electric_consumption(self):
        """Long term average electric enginge consumption."""
        return self._data.get("longTerm", {}).get("averageElectricEngineConsumption", None)

    @property
    def longterm_fuel_consumption(self):
        """Long term average fuel consumption."""
        return self._data.get("longTerm", {}).get("averageFuelConsumption", None)

    @property
    def longterm_recuperation(self):
        """Long term average fuel consumption."""
        return self._data.get("longTerm", {}).get("averageRecuperation", None)

    @property
    def longterm_average_speed(self):
        """Long term average speed."""
        return self._data.get("longTerm", {}).get("averageSpeed", None)

    @property
    def longterm_distance(self):
        """Long term distance traveled."""
        return self._data.get("longTerm", {}).get("mileage", None)

    @property
    def longterm_start_mileage(self):
        """Long term odometer start value."""
        return self._data.get("longTerm", {}).get("startMileage", None)

    @property
    def longterm_time_traveled(self):
        """Time traveled since last long-term reset."""
        return self._data.get("longTerm", {}).get("traveltime", None)


class MBBPosition(MBBDataModel):
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        super.__init__(data)

    @property
    def latitude(self):
        """GPS latitude coordinate."""
        return (
            self._data.get("findCarResponse", {})
            .get("Position", {})
            .get("carCoordinate", {})
            .get("latitude", "?")
        )

    @property
    def longitude(self):
        """GPS latitude coordinate."""
        return (
            self._data.get("findCarResponse", {})
            .get("Position", {})
            .get("carCoordinate", {})
            .get("longitude", "?")
        )

    @property
    def longitude(self):
        """GPS latitude coordinate."""
        return self._data.get("findCarResponse", {}).get("parkingTimeUTC", None)


class MBBDeparture(MBBDataModel):
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        super.__init__(data)

    @property
    def min_charge_level(self):
        """Minimum charge level."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerBasicSetting", {})
            .get("chargeMinLimit", None)
        )

    @property
    def heater_source(self):
        """Heater source for next departure."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerBasicSetting", {})
            .get("heaterSource", None)
        )

    @property
    def departure1(self) -> dict:
        """Departure schedule 1."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerList", {})
            .get("timer", [])[0]
        )

    @property
    def departure2(self) -> dict:
        """Departure schedule 2."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerList", {})
            .get("timer", [])[1]
        )

    @property
    def departure3(self) -> dict:
        """Departure schedule 3."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerList", {})
            .get("timer", [])[2]
        )

    @property
    def departure1_profile(self) -> dict:
        """Departure schedule 1 profile."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerProfileList", {})
            .get("timerProfile", [])[0]
        )

    @property
    def departure2_profile(self) -> dict:
        """Departure schedule 2 profile."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerProfileList", {})
            .get("timerProfile", [])[1]
        )

    @property
    def departure3_profile(self) -> dict:
        """Departure schedule 3 profile."""
        return (
            self._data.get("timer", {})
            .get("timersAndProfiles", {})
            .get("timerProfileList", {})
            .get("timerProfile", [])[2]
        )


class MBBParkingHeater(MBBDataModel):
    """Data model class representing the MBB API endpoints structure."""

    def __init__(self, data: dict = None):
        """Init class."""
        super.__init__(data)

    @property
    def climatisation_state(self):
        """Climatisation state."""
        return self._data.get("statusResponse", {}).get("climatisationStateReport", {})

    @property
    def climatisation_settings(self):
        """Climatisation settings."""
        return self._data.get("statusResponse", {}).get("climatisationSettingsReport", {})

    @property
    def temperature(self):
        """Outdoor temperature."""
        return self._data.get("statusResponse", {}).get("climatisationTemperatureReport", {})

    @property
    def parked_time(self):
        """Vehicle parked timestamp."""
        return self._data.get("statusResponse", {}).get("vehicleParkingClock", {})

    @property
    def departure1(self):
        """Vehicle departure schedule 1."""
        return (
            self._data.get("statusResponse", {})
            .get("departureTimersReport", {})
            .get("departureTimer", [])[0]
        )

    @property
    def departure2(self):
        """Vehicle departure schedule 2."""
        return (
            self._data.get("statusResponse", {})
            .get("departureTimersReport", {})
            .get("departureTimer", [])[1]
        )

    @property
    def departure3(self):
        """Vehicle departure schedule 3."""
        return (
            self._data.get("statusResponse", {})
            .get("departureTimersReport", {})
            .get("departureTimer", [])[2]
        )

    @property
    def heater_mode(self):
        """Vehicle departure schedule 3."""
        return (
            self._data.get("statusResponse", {})
            .get("departureTimersReport", {})
            .get("heaterMode", None)
        )
