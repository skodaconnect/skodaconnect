![Version](https://img.shields.io/github/v/release/lendy007/skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads PyPi](https://img.shields.io/pypi/dm/skodaconnect)

# Skoda Connect v1.0.30-RC5

Fork of https://github.com/robinostlund/volkswagencarnet where it was modified to support also Skoda Connect.
Changes made to utilize the same API calls as the MySkoda mobile app.

## Information

Retrieve statistics about your Skoda from the Skoda Connect online service

No licence, public domain, no guarantees, feel free to use for anything. Please contribute improvements/bugfixes etc.

## Breaking changes

Major code changes have been made to consolidate functions and also enable auxiliary climatisation for PHEV vehicles.
Names have been changed to avoid confusion when working with the code.

- **From version 1.0.30** and onwards there might be breaking changes for the combustion heating/climatisation.

- **Parking Heater** is the auxiliary/parking heater for **non-PHEV** vehicles. This uses the "legacy" remotestandheizung API function.
Heating is what it sounds like and ventilation is used to ventilate/cool the car.

- **Auxiliary Heater** is the auxiliary/parking heater for **PHEV** vehicles. This uses the climater API function, same as electric climatisation.

## Thanks to

- [RobinostLund](https://github.com/robinostlund/volkswagencarnet) for initial project for Volkswagen Carnet I was able to fork
- [Farfar](https://github.com/Farfar) for modifications related to electric engines
- [tanelvakker](https://github.com/tanelvakker) for modifications related to correct SPIN handling for various actions and using correct URLs also for MY2021

## Other related repositories

- [HomeAssistant Component](https://github.com/lendy007/homeassistant-skodaconnect) a custom component for Home Assistant

## Installation

```sh
[venv-python3] user@localhost:~
$ pip install skodaconnect
```

### Example

```python
#!/usr/bin/env python3
import skodaconnect
import pprint
import asyncio
import logging

from aiohttp import ClientSession

logging.basicConfig(level=logging.DEBUG)

USERNAME='test@example.com'
PASSWORD='mysecretpassword'


COMPONENTS = {
    'sensor': 'sensor',
    'binary_sensor': 'binary_sensor',
    'lock': 'lock',
    'device_tracker': 'device_tracker',
    'switch': 'switch',
}

RESOURCES = [
        - charging_cable_connected
        - charging_cable_locked
        - door_closed_left_front
        - door_closed_left_back
        - door_closed_right_front
        - door_closed_right_back
        - doors_locked
        - energy_flow
        - external_power
        - hood_closed
        - parking_light
        - request_in_progress
        - sunroof_closed
        - trunk_closed
        - trunk_locked
        - vehicle_moving
        - window_closed_left_front
        - window_closed_left_back
        - window_closed_right_front
        - window_closed_right_back
        - windows_closed
        - position
        - door_locked
        - trunk_locked
        - adblue_level
        - battery_level
        - charger_max_ampere
        - charging_time_left
        - climatisation_target_temperature
        - combined_range
        - combustion_range
        - electric_range
        - fuel_level
        - last_connected
        - last_trip_average_electric_consumption
        - last_trip_average_fuel_consumption
        - last_trip_average_speed
        - last_trip_duration
        - last_trip_length
        - odometer
        - oil_inspection_days
        - oil_inspection_distance
        - outside_temperature
        - parking_time
        - pheater_status
        - pheater_duration
        - request_results
        - requests_remaining
        - service_inspection_days
        - service_inspection_distance
        - auxiliary_climatisation
        - charging
        - climatisation_from_battery
        - electric_climatisation
        - force_data_refresh
        - parking_heater_heating
        - parking_heater_ventilation
        - window_heater
]

def is_enabled(attr):
    """Return true if the user has enabled the resource."""
    return attr in RESOURCES

async def main():
    """Main method."""
    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        connection = skodaconnect.Connection(session, USERNAME, PASSWORD)
        if await connection._login():
            if await connection.update():
                # Print overall state
                pprint.pprint(connection._state)

                # Print vehicles
                for vehicle in connection.vehicles:
                    pprint.pprint(vehicle)

                # get all instruments
                instruments = set()
                for vehicle in connection.vehicles:
                    dashboard = vehicle.dashboard(mutable=True)

                    for instrument in (
                            instrument
                            for instrument in dashboard.instruments
                            if instrument.component in COMPONENTS
                            and is_enabled(instrument.slug_attr)):

                        instruments.add(instrument)

                # Output all supported instruments
                for instrument in instruments:
                    print(f'name: {instrument.full_name}')
                    print(f'str_state: {instrument.str_state}')
                    print(f'state: {instrument.state}')
                    print(f'supported: {instrument.is_supported}')
                    print(f'attr: {instrument.attr}')
                    print(f'attributes: {instrument.attributes}')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # loop.run(main())
    loop.run_until_complete(main())
``` 
