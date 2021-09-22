#!/usr/bin/env python3
import pprint
import asyncio
import logging
import inspect
import time
import sys
import os

from paho.mqtt import client as mqtt_client
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

#logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.ERROR)

USERNAME = 'skodaUserName'
PASSWORD = 'skodaPWD'
PRINTRESPONSE = False
INTERVAL = 20

broker = 'xx.xx.xx.xx'
port = 1883
topic = "/monTopic"
client_id = f'skoda-mqtt'

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
    # Set Connecting Client ID
    client = mqtt_client.Client(client_id)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client



COMPONENTS = {
    'sensor': 'sensor',
    'binary_sensor': 'binary_sensor',
    'lock': 'lock',
    'device_tracker': 'device_tracker',
    'switch': 'switch',
}

RESOURCES = [
#		"adblue_level",
#		"auxiliary_climatisation",
		"battery_level",
#		"charge_max_ampere",
		"charger_action_status",
		"charging",
#        "charge_rate",
#        "charging_power",
		"charging_cable_connected",
		"charging_cable_locked",
		"charging_time_left",
#		"climater_action_status",
#		"climatisation_target_temperature",
#		"climatisation_without_external_power",
#		"combined_range",
#		"combustion_range",
#        "departure1",
#        "departure2",
#        "departure3",
#		"distance",
#		"door_closed_left_back",
#		"door_closed_left_front",
#		"door_closed_right_back",
#		"door_closed_right_front",
#		"door_locked",
#		"electric_climatisation",
#		"electric_range",
#		"energy_flow",
		"external_power"
#		"fuel_level",
#		"hood_closed",
#		"last_connected",
#		"lock_action_status",
#		"oil_inspection",
#		"oil_inspection_distance",
#		"outside_temperature",
#		"parking_light",
#		"parking_time",
#		"pheater_heating",
#		"pheater_status",
#		"pheater_ventilation",
#		"position",
#		"refresh_action_status",
#		"refresh_data",
 #       "request_flash",
  #      "request_honkandflash",
#		"request_in_progress",
#		"request_results",
#		"requests_remaining",
#		"service_inspection",
#		"service_inspection_distance",
#		"sunroof_closed",
#		"trip_last_average_auxillary_consumption",
#		"trip_last_average_electric_consumption",
#		"trip_last_average_fuel_consumption",
#		"trip_last_average_speed",
#		"trip_last_duration",
#		"trip_last_entry",
#		"trip_last_length",
#		"trip_last_recuperation",
#		"trip_last_total_electric_consumption",
#		"trunk_closed",
#		"trunk_locked",
#		"vehicle_moving",
#		"window_closed_left_back",
#		"window_closed_left_front",
#		"window_closed_right_back",
#		"window_closed_right_front",
#		"window_heater",
#		"windows_closed",
 #       "seat_heating"
]

def is_enabled(attr):
    """Return true if the user has enabled the resource."""
    return attr in RESOURCES

async def main():
    """Main method."""
    client = connect_mqtt()
    client.loop_start()

    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        print('########################################')
        print('#      Logging on to Skoda Connect     #')
        print('########################################')
        connection = Connection(session, USERNAME, PASSWORD, PRINTRESPONSE)
        print("Attempting to login to the Skoda Connect service")
        if await connection.doLogin():
            print('Login success!')
            print('Fetching vehicles associated with account.')
            await connection.get_vehicles()

            instruments = set()
            for vehicle in connection.vehicles:
                print('')
                print('########################################')
                print('#         Setting up dashboard         #')
                print('########################################')
                dashboard = vehicle.dashboard(mutable=True)

                for instrument in (
                        instrument
                        for instrument in dashboard.instruments
                        if instrument.component in COMPONENTS
                        and is_enabled(instrument.slug_attr)):

                    instruments.add(instrument)
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
            client.publish(f'vehicule/{instrument.vehicle_name}/{instrument.attr}', f'{instrument.state}', 1 )
            print(f'{instrument.full_name} - ({instrument.attr})')
            print(f'\tstr_state: {instrument.str_state} - state: {instrument.state}')
            print(f'\tattributes: {instrument.attributes}')
            print("")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

