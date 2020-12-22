![Version](https://img.shields.io/github/v/release/lendy007/skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads](https://img.shields.io/github/downloads/lendy007/skodaconnect/total)
![Downloads PyPi](https://img.shields.io/pypi/dm/skodaconnect)

# Skoda Connect v1.0.26

Fork of https://github.com/robinostlund/volkswagencarnet where it was modified to support also Skoda Connect

## Information

Retrieve statistics about your Skoda from the Skoda Connect online service

No licence, public domain, no guarantees, feel free to use for anything. Please contribute improvements/bugfixes etc.

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
    'climate': 'climate'
}

RESOURCES = [
    'position',
    'distance',
    'electric_climatisation',
    'combustion_climatisation',
    'window_heater',
    'combustion_engine_heating',
    'charging',
    'adblue_level',
    'battery_level',
    'fuel_level',
    'service_inspection',
    'service_inspection_km',
    'oil_inspection',
    'oil_inspection_km',
    'last_connected',
    'charging_time_left',
    'electric_range',
    'combustion_range',
    'combined_range',
    'charge_max_ampere',
    'climatisation_target_temperature',
    'external_power',
    'energy_flow',
    'parking_light',
    'climatisation_without_external_power',
    'door_locked',
    'trunk_locked',
    'request_in_progress',
    'windows_closed',
    'sunroof_closed',
    'trip_last_average_speed',
    'trip_last_average_electric_consumption',
    'trip_last_average_fuel_consumption',
    'trip_last_duration',
    'trip_last_length',
    'outside_temperature'
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
