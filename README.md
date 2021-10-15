![Version](https://img.shields.io/github/v/release/lendy007/skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads PyPi](https://img.shields.io/pypi/dm/skodaconnect)

# Skoda Connect v1.1.10
Fork of https://github.com/robinostlund/volkswagencarnet where it was modified to support also Skoda Connect.
Changes made to utilize the same API calls as the MySkoda mobile app.

## Information

Retrieve statistics about your Skoda from the Skoda Connect online service.
* Support for Skoda Connect services
* Support for SmartLink
* All (native) Skoda cars supported though newer cars (Skoda Enyaq iV) use newer API that's under development
* If your Skoda car don't work with the MySkoda app it won't work with this integration

No licence, public domain, no guarantees, feel free to use for anything. Please contribute improvements/bugfixes etc.

## Breaking changes

- **From version 1.1.0** and onwards there has been changes to token handling, login procedure and overall mode streamlined code. Logins should now be significantly faster and reliable.

- **From version 1.0.40** and onwards there has been changes to Skoda API and this might break the integration for some cars.

- **From version 1.0.30** and onwards there might be breaking changes for the combustion heating/climatisation.

- **Parking Heater** is the auxiliary/parking heater for **non-PHEV** vehicles. This uses the "legacy" remotestandheizung API function.
Heating is what it sounds like and ventilation is used to ventilate/cool the car.

- **Auxiliary Heater** is the auxiliary/parking heater for **PHEV** vehicles. This uses the climater API function, same as electric climatisation.

## Thanks to

- [RobinostLund](https://github.com/robinostlund/volkswagencarnet) for initial project for Volkswagen Carnet which this is based on initially
- [Farfar](https://github.com/Farfar) for modifications related to electric engines
- [tanelvakker](https://github.com/tanelvakker) for modifications related to correct SPIN handling for various actions and using correct URLs also for MY2021
- [wieshka](https://github.com/wieshka) for help with Skoda Enyaq iV development

## Other related repositories

- [HomeAssistant Component](https://github.com/lendy007/homeassistant-skodaconnect) a custom component for Home Assistant

## Installation

```sh
[venv-python3] user@localhost:~
$ pip install skodaconnect
```

### Example

For an extensive example, please use the code found in example/example.py.
When logged in the library will automatically create a vehicle object for every car registered to the account. Initially no data is fetched at all. Use the doLogin method and it will signin with the credentials used for the class constructor.
Method get_vehicles will fetch vehicle basic information and create Vehicle class objects for all associated vehicles in account.
To update all available data use the update_all method of the Connect class. This will call the update function for all registered vehicles, which in turn will fetch data from all available API endpoints.

#### Attributes
The Vehicle class contains all of the attributes with values fetched from the API.
To access a single attribute, please see and use the example/example.py.
This will print all available methods, variables and properties as well as a list of supported attributes for discovered car.

#### Methods
Vehicle, in the following example the car object is an object of Vehicle class:
```
car.set_charger(action = "start")                          # action = "start" or "stop"
car.set_charger_current(value=<int/str>                    # value = integer 1-255 or Maximum/Reduced (For PHEV: 252=Reduced and 254=Maximum)
car.set_charge_limit(value=<int>)                          # value = integer 0-100 in 10 increments. Valid values is PHEV: 0-50, EV: 50-100.
car.set_battery_climatisation(mode = False)                # mode = False or True
car.set_climatisation(mode = "auxilliary", spin="1234")    # mode = "auxilliary", "electric" or "off". spin is S-PIN and only needed for aux heating
car.set_climatisation_temp(temperature = 22)               # temperature = integer from 16 to 30
car.set_window_heating(action = "start")                   # action = "start" or "stop"
car.set_lock(action = "unlock", spin = "1234")             # action = "unlock" or "lock". spin = SPIN, needed for both
car.set_pheater(mode = "heating", spin = "1234")           # action = "heating", "ventilation" or "off". spin = SPIN, not needed for off
car.set_charge_limit(limit = 30)                           # limit = 0,10,20,30,40,50
car.set_timer_active(id = 1, action = "on"}                # id = 1, 2, 3, action = "on" or "off".
car.set_timer_schedule(id = 1,  schedule = dict)           # id = 1, 2, 3, see example for full information about schedule variable
car.set_refresh()                                          # Takes no arguments, will trigger force update
```

Connection:
```
session = aiohttp.ClientSession(headers={'Connection': 'keep-alive'})   # Create a aiohttp session object
conn = Connection(session, username, password, fulldebug)               #
conn.doLogin()                                                         # Attempt a login, returns true/false, variable conn.
conn.get_vehicles()                                                     # Attempts to fetch all vehicles associated to account.
conn.update_all()                                                       # Calls update for all vehicle objects.
conn.logout()                                                           # Logout from API, call for revoke of tokens.
conn.terminate()                                                        # Terminate session, calls logout().
conn.get<method>                                                        # The get methods calls on API endpoints and returns data. See example.
conn.set<method>                                                        # The set methods calls on API endpoints to set config for vehicle.
```
Refrain from using methods starting with _, they are intended for internal use only.

## Further help or contributions
For questions, further help or contributions you can join the Discord server at https://discord.gg/826X9jEtCh
