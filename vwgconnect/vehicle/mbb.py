#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abstract base class for Vehicle data model.
Models methods and properties common for all vehicle classes.
"""

from __future__ import annotations
from vwgconnect.platform import MBB
from .base import Car
from .const import HOMEREGION, BASEURI, CONTENT


class MBBCar(Car):
    """MBB Car data model."""

    def __init__(self: Car, client: MBB, vin: str) -> None:
        """
        Init MBB Skoda Car data model class

        Arguments:
            client: class, MBB API Client class instance to use for interaction with the car
            vin: str, vehicle vin number
        """
        super.__init__(conn=client, vin=vin)
        self.homeregion = False

    async def update(self):
        """Update car status information."""
        # First make sure that our home region is set, else fetch it
        if not self.homeregion:
            url_response = await self.platform.home_region(self.vin)
            self.homeregion = url_response.get(HOMEREGION, {}).get(BASEURI, {}).get(CONTENT, None)
        # Fetch operationlist

    # Properties of class instance
    # Car general information
    @property
    def vin(self):
        """Return car vin number."""

    @property
    def nickname(self):
        """Return car nickname as named in app."""

    @property
    def deactivated(self):
        """Return status of car activation."""

    @property
    def model(self):
        """Return model."""

    @property
    def model_year(self):
        """Return model year."""

    @property
    def model_image_small(self):
        """Return URL for model image."""

    @property
    def model_image_large(self):
        """Return URL for model image."""

    # Battery
    @property
    def battery_capacity(self):
        """Return battery capacity."""

    @property
    def max_charging_power(self):
        """Return maximum charger current."""

    # Engine
    @property
    def engine_power(self):
        """Return engine power in kW."""

    @property
    def engine_type(self):
        """Return type of engine."""

    @property
    def engine_capacity(self):
        """Return engine capacity in liters."""

    # Lights
    @property
    def parking_light(self):
        """Return true if parking light is on"""

    # Connection status
    @property
    def last_connected(self):
        """Return when vehicle was last connected to connect servers."""

    # Service information
    @property
    def odometer(self):
        """Return vehicle odometer."""

    @property
    def service_inspection(self):
        """Return time left until service inspection"""

    @property
    def service_inspection_distance(self):
        """Return time left until service inspection"""

    @property
    def oil_inspection(self):
        """Return time left until oil inspection"""

    @property
    def oil_inspection_distance(self):
        """Return distance left until oil inspection"""

    @property
    def adblue_level(self):
        """Return adblue level."""

    # Charger related states for EV and PHEV
    @property
    def charge_level(self):
        """Return level of charge."""

    @property
    def charger_state(self):
        """Return charging state."""

    @property
    def min_charge_level(self):
        """Return the charge level that car charges directly to"""

    @property
    def plug_autounlock(self):
        """Return the state of plug auto unlock at charged"""

    @property
    def charge_max_ampere(self):
        """Return charger max ampere setting."""

    @property
    def charging_cable_locked(self):
        """Return plug locked state"""

    @property
    def charging_cable_connected(self):
        """Return plug locked state"""

    @property
    def charging_time_left(self):
        """Return minutes to charging complete"""

    @property
    def charging_power(self):
        """Return charging power in watts."""

    @property
    def charge_rate(self):
        """Return charge rate in km per h."""

    @property
    def external_power(self):
        """Return true if external power is connected."""

    @property
    def energy_flow(self):
        """Return true if energy is flowing through charging port."""

    # Vehicle location states
    @property
    def position(self):
        """Return  position."""

    @property
    def vehicle_moving(self):
        """Return true if vehicle is moving."""

    @property
    def parking_time(self):
        """Return timestamp of last parking time."""

    # Vehicle fuel level and range
    @property
    def primary_range(self):
        """Return range of primary engine."""

    @property
    def primary_drive(self):
        """Return primary drive type."""

    @property
    def secondary_range(self):
        """Return range of secondary engine."""

    @property
    def secondary_drive(self):
        """Return secondary drive type."""

    @property
    def combined_range(self):
        """Return combined range."""

    @property
    def fuel_level(self):
        """Return fuel level."""

    # Climatisation settings
    @property
    def climatisation_target_temperature(self):
        """Return the target temperature from climater."""

    @property
    def climatisation_time_left(self):
        """Return time left for climatisation in hours:minutes."""

    @property
    def climatisation_without_external_power(self):
        """Return state of climatisation from battery power."""

    @property
    def outside_temperature(self):
        """Return outside temperature."""

    # Climatisation status
    @property
    def electric_climatisation_attributes(self):
        """Return climatisation attributes."""

    @property
    def electric_climatisation(self):
        """Return status of climatisation."""

    @property
    def auxiliary_climatisation(self):
        """Return status of auxiliary climatisation."""

    @property
    def aux_heater_for_departure(self):
        """Return status of aux heater for next departure."""
        if self.departure1.get("heaterSource", "electric") == "automatic":
            return True
        return False

    @property
    def aircon_at_unlock(self):
        """Return status of air-conditioning at unlock setting."""

    @property
    def climatisation_window_heat(self):
        """Return window heat during climatisation setting."""

    @property
    def window_heater(self):
        """Return status of window heater."""

    @property
    def window_heater_attributes(self):
        """Return window heater attributes."""

    @property
    def seat_heating_front_left(self):
        """Return status of seat heating front left."""

    @property
    def seat_heating_front_right(self):
        """Return status of seat heating front right."""

    @property
    def seat_heating_rear_left(self):
        """Return status of seat heating rear left."""

    @property
    def seat_heating_rear_right(self):
        """Return status of seat heating rear right."""

    # Parking heater, "legacy" auxiliary climatisation
    @property
    def pheater_duration(self):
        """Return parking heater runtime."""

    @property
    def pheater_status(self):
        """Return status of combustion engine heating/ventilation."""

    # Windows
    @property
    def windows_closed(self):
        """Return status of windows."""

    @property
    def window_closed_left_front(self):
        """Return status of left front window."""

    @property
    def window_closed_right_front(self):
        """Return status of right front window."""

    @property
    def window_closed_left_back(self):
        """Return status of left back window."""

    @property
    def window_closed_right_back(self):
        """Return status of right back window."""

    @property
    def sunroof_closed(self):
        """Return status of sunroof."""

    # Locks
    @property
    def door_locked(self):
        """Return status of door locks."""

    @property
    def trunk_locked(self):
        """Return status of trunk lock."""

    # Doors, hood and trunk
    @property
    def hood_closed(self):
        """Return true if hood is closed"""

    @property
    def door_closed_left_front(self):
        """Return status of left front door."""

    @property
    def door_closed_right_front(self):
        """Return status of right front door."""

    @property
    def door_closed_left_back(self):
        """Return status of left back door."""

    @property
    def door_closed_right_back(self):
        """Return status of right back door."""

    @property
    def trunk_closed(self):
        """Return status of trunk."""

    # Departure timers
    @property
    def departure1(self):
        """Return timer status and attributes."""

    @property
    def departure2(self):
        """Return timer status and attributes."""

    @property
    def departure3(self):
        """Return timer status and attributes."""

    # Trip last data
    @property
    def trip_last_entry(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_average_speed(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_average_electric_consumption(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_average_fuel_consumption(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_average_auxillary_consumption(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_average_aux_consumer_consumption(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_duration(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_length(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_recuperation(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_average_recuperation(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_total_electric_consumption(self):
        """Trip statistics for last trip."""

    @property
    def trip_last_start_mileage(self):
        """Trip statistics for last trip."""

    # Trip statistics longterm
    @property
    def trip_longterm_entry(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_average_speed(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_average_electric_consumption(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_average_fuel_consumption(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_average_auxillary_consumption(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_average_aux_consumer_consumption(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_duration(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_length(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_recuperation(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_average_recuperation(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_total_electric_consumption(self):
        """Trip statistics for long term."""

    @property
    def trip_longterm_start_mileage(self):
        """Trip statistics for long term."""

    # Status of set data requests
    @property
    def refresh_action_status(self):
        """Return latest status of data refresh request."""

    @property
    def refresh_action_timestamp(self):
        """Return timestamp of latest data refresh request."""

    @property
    def charger_action_status(self):
        """Return latest status of charger request."""

    @property
    def charger_action_timestamp(self):
        """Return timestamp of latest charger request."""

    @property
    def aircon_action_status(self):
        """Return latest status of air-conditioning request."""

    @property
    def aircon_action_timestamp(self):
        """Return timestamp of latest air-conditioning request."""

    @property
    def climater_action_status(self):
        """Return latest status of climater request."""

    @property
    def climater_action_timestamp(self):
        """Return timestamp of latest climater request."""

    @property
    def pheater_action_status(self):
        """Return latest status of parking heater request."""

    @property
    def pheater_action_timestamp(self):
        """Return timestamp of latest parking heater request."""

    @property
    def honkandflash_action_status(self):
        """Return latest status of honk and flash action request."""

    @property
    def honkandflash_action_timestamp(self):
        """Return timestamp of latest honk and flash request."""

    @property
    def lock_action_status(self):
        """Return latest status of lock action request."""

    @property
    def lock_action_timestamp(self):
        """Return timestamp of latest lock action request."""

    @property
    def timer_action_status(self):
        """Return latest status of departure timer request."""

    @property
    def timer_action_timestamp(self):
        """Return timestamp of latest departure timer request."""

    @property
    def refresh_data(self):
        """Get state of data refresh"""

    @property
    def is_refresh_data_supported(self):
        """Data refresh is supported."""

    # Requests data
    @property
    def request_in_progress(self):
        """Returns the current, or latest, request in progress."""

    @property
    def request_results(self):
        """Get last request result."""

    @property
    def requests_remaining(self):
        """Get remaining requests before throttled."""
