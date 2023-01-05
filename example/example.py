#!/usr/bin/env python3
import pprint
import asyncio
import logging
import inspect
import time
import sys
import os
from aiohttp import ClientSession
from datetime import datetime

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

try:
    from skodaconnect import Connection
except ModuleNotFoundError as e:
    print(f"Unable to import library: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG)

USERNAME = 'email@domain.com'
PASSWORD = 'password!'
PRINTRESPONSE = False
MILES = False
INTERVAL = 20

# If you wish to use stored tokens, this is an example on how to format data sent to restore_tokens method
# Populate each 'client' as needed with the refresh_token as it can be used to fetch new access, id and refresh tokens
# The known clients are: technical, connect, "vwg", cabs and dcs. The main client is "technical" and can be used to fetch the rest
TOKENS = {
    'technical': 'TOKENDATA',
    'connect': 'TOKENDATA',
    'vwg': None,    # You can store and restore this refresh token but it's more robust to reauth the vwg client
    'cabs': None,   # Not sure if this is used and in that case for what
    'dcs': None,    # Smartlink
}
# Comment out the following line to use stored tokens above, set TOKENS=None to do fresh login
TOKENS = None

COMPONENTS = {
    'sensor': 'sensor',
    'binary_sensor': 'binary_sensor',
    'lock': 'lock',
    'device_tracker': 'device_tracker',
    'switch': 'switch',
}

# Set to true to enable all resources
RESOURCES_ALL = True
# OR set above to False and comment out resources in this list to disable them
RESOURCES = [
		"adblue_level",
        "aircon_at_unlock",
		"auxiliary_climatisation",
		"battery_level",
		"charge_max_ampere",
		"charger_action_status",
		"charging",
        "charge_rate",
        "charging_power",
		"charging_cable_connected",
		"charging_cable_locked",
		"charging_time_left",
		"climater_action_status",
		"climatisation_target_temperature",
		"climatisation_without_external_power",
		"combined_range",
		"combustion_range",
        "departure1",
        "departure2",
        "departure3",
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
        "model",
		"oil_inspection",
		"oil_inspection_distance",
		"outside_temperature",
		"parking_light",
		"parking_time",
		"pheater_heating",
		"pheater_status",
		"pheater_ventilation",
        "plug_autounlock",
		"position",
		"refresh_action_status",
		"refresh_data",
        "request_flash",
        "request_honkandflash",
		"request_in_progress",
		"request_results",
		"requests_remaining",
        "seat_heating_front_left",
        "seat_heating_front_right",
        "seat_heating_rear_left",
        "seat_heating_rear_right",
		"service_inspection",
		"service_inspection_distance",
		"sunroof_closed",
		"trip_last_average_auxillary_consumption",
        "trip_last_average_aux_consumer_consumption",
		"trip_last_average_electric_consumption",
		"trip_last_average_fuel_consumption",
        "trip_last_average_recuperation",
		"trip_last_average_speed",
		"trip_last_duration",
		"trip_last_entry",
		"trip_last_length",
		"trip_last_recuperation",
		"trip_last_total_electric_consumption",
        "trip_last_start_mileage",
		"trip_longterm_average_auxillary_consumption",
        "trip_longterm_average_aux_consumer_consumption",
		"trip_longterm_average_electric_consumption",
		"trip_longterm_average_fuel_consumption",
        "trip_longterm_average_recuperation",
		"trip_longterm_average_speed",
		"trip_longterm_duration",
		"trip_longterm_entry",
		"trip_longterm_length",
		"trip_longterm_recuperation",
		"trip_longterm_total_electric_consumption",
        "trip_longterm_start_mileage",
		"trunk_closed",
		"trunk_locked",
		"vehicle_moving",
		"window_closed_left_back",
		"window_closed_left_front",
		"window_closed_right_back",
		"window_closed_right_front",
		"window_heater",
        "window_heater_new",
		"windows_closed",
        "seat_heating"
]

def is_enabled(attr):
    """Return true if the user has enabled the resource."""
    if RESOURCES_ALL is True:
        return True
    return attr in RESOURCES

async def main():
    """Main method."""
    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        login_success = False
        print('')
        print('########################################')
        print('#      Logging on to Skoda Connect     #')
        print('########################################')
        print(f"Initiating new session to Skoda Connect with {USERNAME} as username")
        try:
            connection = Connection(session, USERNAME, PASSWORD, PRINTRESPONSE)
            if TOKENS is not None:
                print("Attempting restore of tokens")
                if await connection.restore_tokens(TOKENS):
                    print("Token restore succeeded")
                    login_success = True
            if not login_success:
                print("Attempting to login to the Skoda Connect service")
                login_success = await connection.doLogin()
        except Exception as e:
            print(f"Login failed: {e}")
            exit()

        if login_success:
            print('Login success!')
            print(datetime.now())
            print('Fetching vehicles associated with account.')
            try:
                await connection.get_vehicles()
            except Exception as e:
                print(f'Error encountered when fetching vehicles: {e}')
                exit()

            # Need to get data before we know what sensors are available
            print('Fetch latest data for all vehicles.')
            try:
                await connection.update_all()
            except Exception as e:
                print(f'Error encountered when fetching vehicle data: {e}')
                exit()

            instruments = set()
            for vehicle in connection.vehicles:
                print('')
                print('########################################')
                print('#         Setting up dashboard         #')
                print('########################################')
                try:
                    dashboard = vehicle.dashboard(mutable=True, miles=MILES)
                    for instrument in (
                            instrument
                            for instrument in dashboard.instruments
                            if instrument.component in COMPONENTS
                            and is_enabled(instrument.slug_attr)):
                        instruments.add(instrument)
                except Exception as e:
                    print(f'Failed to load instruments: {e}')
                    exit()

            print('')
            print('########################################')
            print('#          Vehicles discovered         #')
            print('########################################')
            for vehicle in connection.vehicles:
                print(f"\tVIN: {vehicle.vin}")
                print(f"\tModel: {vehicle.model}")
                print(f"\tManufactured: {vehicle.model_year}")
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

        # Output all instruments and states
        print('')
        print('########################################')
        print('#      Instruments from dashboard      #')
        print('########################################')
        inst_list = sorted(instruments, key=lambda x: x.attr)
        for instrument in inst_list:
            print(f'{instrument.full_name} - ({instrument.attr})')
            print(f'\tstr_state: {instrument.str_state} - state: {instrument.state}')
            print(f'\tattributes: {instrument.attributes}')
            print("")

        print('')
        print(f"Sleeping for {INTERVAL} seconds")
        time.sleep(INTERVAL)

        print('')
        print(datetime.now())
        print('')
        print('########################################')
        print('#    Updating all values from Skoda    #')
        print('########################################')
        print("Updating ALL values from Skoda Connect...")
        if await connection.update_all():
            print("Success!")
        else:
            print("Failed")

        # Sleep for a given ammount of time and update individual API endpoints for each vehicle
        print('')
        print(f"Sleeping for {INTERVAL} seconds")
        time.sleep(INTERVAL)

        for vehicle in connection.vehicles:
            txt = vehicle.vin
            print('')
            print(datetime.now())
            print('')
            print('########################################')
            print('#          Update charger data         #')
            print(txt.center(40, '#'))
            await vehicle.get_charger()
            print('')
            print('########################################')
            print('#         Update climater data         #')
            print(txt.center(40, '#'))
            await vehicle.get_climater()
            print('')
            print('########################################')
            print('#         Update position data         #')
            print(txt.center(40, '#'))
            await vehicle.get_position()
            print('')
            print('########################################')
            print('#         Update preheater data        #')
            print(txt.center(40, '#'))
            await vehicle.get_preheater()
            print('')
            print('########################################')
            print('#          Update realcar data         #')
            print(txt.center(40, '#'))
            await vehicle.get_realcardata()
            print('')
            print('########################################')
            print('#          Update status data          #')
            print(txt.center(40, '#'))
            await vehicle.get_statusreport()
            print('')
            print('########################################')
            print('#       Update timer programming       #')
            print(txt.center(40, '#'))
            await vehicle.get_timerprogramming()
            print('')
            print('########################################')
            print('#        Update trip statistics        #')
            print(txt.center(40, '#'))
            await vehicle.get_trip_statistic()
            print('')
            print('Updates complete')

            print(f"Sleeping for {INTERVAL} seconds")
            time.sleep(INTERVAL)
            # Examples for using set functions:
            #vehicle.set_refresh()                                          # Takes no arguments, will trigger forced update
            #vehicle.set_charger(action = "start")                          # action = "start" or "stop"
            #vehicle.set_charger_current(value)                             # value = 1-255/Maximum/Reduced (PHEV: 252 for reduced and 254 for max, EV: Maximum/Reduced)
            #vehicle.set_charge_limit(limit = 50)                           # limit = PHEV: 0/10/20/30/40/50, EV: 50/60/70/80/90/100
            #vehicle.set_battery_climatisation(mode = False)                # mode = False or True
            #vehicle.set_climatisation(mode = "auxilliary", spin="1234")    # mode = "auxilliary", "electric" or "off". spin is S-PIN and only needed for aux heating
            #vehicle.set_climatisation_temp(temperature = 22)               # temperature = integer from 16 to 30
            #vehicle.set_window_heating(action = "start")                   # action = "start" or "stop"
            #vehicle.set_lock(action = "unlock", spin = "1234")             # action = "unlock" or "lock". spin = SPIN, needed for both
            #vehicle.set_pheater(mode = "heating", spin = "1234")           # action = "heating", "ventilation" or "off". spin = SPIN, not needed for off
            #vehicle.set_charge_limit(limit = 30)                           # limit = 0,10,20,30,40,50
            #vehicle.set_timer_active(id = 1, action = "on"}                # id = 1, 2, 3, action = "on" or "off".
            #vehicle.set_timer_schedule(id = 1,                             # id = 1, 2, 3
            #    schedule = {                                               # Set the departure time, date and periodicity
            #        "enabled": True,                                       # Set the timer active or not, True or False, required
            #        "recurring": True,                                     # True or False for recurring, required
            #        "date": "2021-05-21",                                  # Date for departure, required if recurring=False
            #        "time": "08:00",                                       # Time for departure, required
            #        "days": "nyynnnn",                                     # Days (mon-sun) for recurring schedule (n=disable, y=enable), required if recurring=True
            #        "nightRateActive": True,                               # True or False Off-peak hours, optional
            #        "nightRateStart": "00:00",                             # Off-peak hours start (HH:mm), optional
            #        "nightRateEnd": "06:00",                               # Off-peak hours end (HH:mm), optional
            #        "operationCharging": True,                             # True or False for charging, optional
            #        "operationClimatisation": True,                        # True or False fro climatisation, optional
            #        "targetTemp": 22,                                      # Target temperature for climatisation, optional
            #    })

            # Example using a set function
            #if await vehicle.set_charge_limit(limit=40):
            #    print("Request completed successfully.")
            #else:
            #    print("Request failed.")
            #print(vehicle.timer_action_status)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())

