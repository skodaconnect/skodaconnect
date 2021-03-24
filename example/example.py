#!/usr/bin/env python3
import pprint
import asyncio
import logging
import time

from aiohttp import ClientSession
from skodaconnect import Connection

logging.basicConfig(level=logging.DEBUG)

USERNAME = 'mail@domain.tld'
PASSWORD = 'password'
PRINTRESPONSE = True
INTERVAL = 20

COMPONENTS = {
    'sensor': 'sensor',
    'binary_sensor': 'binary_sensor',
    'lock': 'lock',
    'device_tracker': 'device_tracker',
    'switch': 'switch',
}

RESOURCES = [
		"adblue_level",
		"auxiliary_climatisation",
		"battery_level",
		"charge_max_ampere",
		"charger_action_status",
		"charging",
		"charging_cable_connected",
		"charging_cable_locked",
		"charging_time_left",
		"climater_action_status",
		"climatisation_target_temperature",
		"climatisation_without_external_power",
		"combined_range",
		"combustion_range",
		"distance",
		"door_closed_left_back",
		"door_closed_left_front",
		"door_closed_right_back",
		"door_closed_right_front",
		"door_locked",
		"electric_climatisation",
		"electric_range",
		"energy_flow",
		"external_power",
		"fuel_level",
		"hood_closed",
		"last_connected",
		"lock_action_status",
		"oil_inspection",
		"oil_inspection_distance",
		"outside_temperature",
		"parking_light",
		"parking_time",
		"pheater_heating",
		"pheater_status",
		"pheater_ventilation",
		"position",
		"refresh_action_status",
		"refresh_data",
		"request_in_progress",
		"request_results",
		"requests_remaining",
		"service_inspection",
		"service_inspection_distance",
		"sunroof_closed",
		"trip_last_average_auxillary_consumption",
		"trip_last_average_electric_consumption",
		"trip_last_average_fuel_consumption",
		"trip_last_average_speed",
		"trip_last_duration",
		"trip_last_entry",
		"trip_last_length",
		"trip_last_recuperation",
		"trip_last_total_electric_consumption",
		"trunk_closed",
		"trunk_locked",
		"vehicle_moving",
		"window_closed_left_back",
		"window_closed_left_front",
		"window_closed_right_back",
		"window_closed_right_front",
		"window_heater",
		"windows_closed"
]

def is_enabled(attr):
    """Return true if the user has enabled the resource."""
    return attr in RESOURCES

async def main():
    """Main method."""
    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        print(f"Initiating new session to Skoda Connect with {USERNAME} as username")
        connection = Connection(session, USERNAME, PASSWORD, PRINTRESPONSE)
        print("Attempting to login to the Skoda Connect service")
        if await connection.doLogin():
            print('Login success!')
            # Login was successful, library should have created class objects for vehicles.
            # Call update to fetch new data for all vehicles
            if await connection.update():
                # Set up dashboard, get instruments
                instruments = set()
                for vehicle in connection.vehicles:
                    dashboard = vehicle.dashboard(mutable=True)

                    for instrument in (
                            instrument
                            for instrument in dashboard.instruments
                            if instrument.component in COMPONENTS
                            and is_enabled(instrument.slug_attr)):

                        instruments.add(instrument)
                print("Vehicles:")
                for vehicle in connection.vehicles:
                    print(f"\tVIN: {vehicle.vin}")
                    print(f"\tModel: {vehicle.model} - {vehicle.model_year}")
                    print(f"\tConnect service deactivated: {vehicle.deactivated}")
                    if vehicle.is_nickname_supported: print(f"\tNickname: {vehicle.nickname}")
                    print(f"\tObject attributes, and methods:")
                    for prop in dir(vehicle):
                        if not "__" in prop:
                            try:
                                func = f"vehicle.{prop}"
                                typ = type(eval(func))
                                print(f"\t\t{prop} - {typ}")
                            except:
                                pass

        else:
            return False

        # Loop forever
        while True:
            localtime = time.localtime()
            result = time.strftime("########## %I:%M:%S %p - NEW LOOP ##########", localtime)
            print("")
            print(result)
            # Output all instruments and states
            for instrument in instruments:
                print(f'{instrument.full_name} - ({instrument.attr})')
                print(f'\tstr_state: {instrument.str_state} - state: {instrument.state}')
                print(f'\tattributes: {instrument.attributes}')
                print("")

            # Sleep for a given ammount of time and update all vehicles
            print(f"Sleeping for {INTERVAL} seconds")
            time.sleep(INTERVAL)
            print("Updating ALL values from Skoda Connect...")
            if await connection.update():
                print("Success!")
            else:
                print("Failed")

            # Sleep for a given ammount of time and update individual API endpoints for each vehicle
            time.sleep(INTERVAL)
            for vehicle in connection.vehicles:
                print(f"Updating INDIVIDUAL values for {vehicle.vin}...")
                print("Updating carportdata...")
                await vehicle.get_carportdata()
                print("Updating charger data...")
                await vehicle.get_charger()
                print("Updating climater data...")
                await vehicle.get_climater()
                print("Updating position data...")
                await vehicle.get_position()
                print("Updating pre-heater data...")
                await vehicle.get_preheater()
                print("Updating realcardata...")
                await vehicle.get_realcardata()
                print("Updating status data...")
                await vehicle.get_statusreport()
                print("Updating timer data...")
                await vehicle.get_timerprogramming()
                print("Updating trip data...")
                await vehicle.get_trip_statistic()
                print("Update done...")

                time.sleep(INTERVAL)
                # Examples for using set functions:
                #vehicle.set_charger(action = "start")                          # action = "start" or "stop"
                #vehicle.set_charger_current(value)                             # value = 1 <=> 255 (PHEV: 252 for reduced and 254 for max)
                #vehicle.set_battery_climatisation(mode = False)                # mode = False or True
                #vehicle.set_climater(data = json, spin = "1234")               # DO NOT USE DIRECTLY - Argument is json formatted data
                #vehicle.set_climatisation(mode = "auxilliary", spin="1234")    # mode = "auxilliary", "electric" or "off". spin is S-PIN and only needed for aux heating
                #vehicle.set_climatisation_temp(temperature = 22)               # temperature = integer from 16 to 30
                #vehicle.set_window_heating(action = "start")                   # action = "start" or "stop"
                #vehicle.set_lock(action = "unlock", spin = "1234")             # action = "unlock" or "lock". spin = SPIN, needed for both
                #vehicle.set_pheater(mode = "heating", spin = "1234")           # action = "heating", "ventilation" or "off". spin = SPIN, not needed for off

                print(f"Force refresh for {vehicle.vin} ...")
                if await vehicle.set_refresh():                                 # Takes no arguments, will trigger force update
                    print("Success!")
                else:
                    print(vehicle.refresh_action_status)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # loop.run(main())
    loop.run_until_complete(main())
