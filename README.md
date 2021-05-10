![Version](https://img.shields.io/github/v/release/lendy007/skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads PyPi](https://img.shields.io/pypi/dm/skodaconnect)

# Skoda Connect v1.0.40-RC3
**WARNING!**
This is a BETA pre-release. Only install if you are having issues with latest stable release. Read release notes for more details.

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

For an extensive example, please use the code found in example/example.py.
When logged in the library will automatically create a vehicle object for every car registered to the account. Initially no data is fetched other than basic information about the car.
To update all available data use the update method of the Connect class. This will call the update function for all registered vehicles, which in turn will fetch data from all available API endpoints.

#### Attributes
The Vehicle class contains all of the attributes with values fetched from the API.
To access a single attribute, please see and use the example/example.py.
This will print all available methods, variables and properties as well as a list of supported attributes for discovered car.

#### Methods
Vehicle, in the following example the car object is an object of Vehicle class:
```
car.set_charger(action = "start")                          # action = "start" or "stop"
car.set_charger_current(value=<int>)                       # value = integer between 1 and 255. Unknown what values to use other than 252 (reduced) and 254 (max) for PHEV
car.set_battery_climatisation(mode = False)                # mode = False or True
car.set_climater(data = json, spin = "1234")               # DO NOT USE DIRECTLY - Argument is json formatted data
car.set_climatisation(mode = "auxilliary", spin="1234")    # mode = "auxilliary", "electric" or "off". spin is S-PIN and only needed for aux heating
car.set_climatisation_temp(temperature = 22)               # temperature = integer from 16 to 30
car.set_window_heating(action = "start")                   # action = "start" or "stop"
car.set_lock(action = "unlock", spin = "1234")             # action = "unlock" or "lock". spin = SPIN, needed for both
car.set_pheater(mode = "heating", spin = "1234")           # action = "heating", "ventilation" or "off". spin = SPIN, not needed for off
car.set_refresh()                                          # Takes no arguments, will trigger force update
```

Connection:
```
session = aiohttp.ClientSession(headers={'Connection': 'keep-alive'})   # Create a aiohttp session object
conn = Connection(session, username, password, fulldebug)               #
conn._login()                                                           # Attempt a login, returns true/false, variable conn._session_logged_in will tell if logged in or not
conn.update()                                                           # Calls update for all vehicle objects
conn.logout()                                                           # Logout from API, call for revoke of tokens
conn.terminate()                                                        # Terminate session, calls logout()
conn.validate_tokens()                                                  # Checks if tokens are OK, trys a refresh if expired
```
