"""
Copied as is from https://gitlab.com/prior99/skoda/-/blob/master/skoda.py

POC using the new API endpoints
"""

from aiohttp import ClientSession, FormData
import logging
import asyncio
from bs4 import BeautifulSoup
import re
import yaml
import json
import hashlib
import base64
import string
import random
import uuid
import sys

_LOGGER = logging.getLogger(__name__)

# Client id for MySkoda app.
CLIENT_ID = "7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com"

BASE_URL_SKODA = "https://mysmob.api.connect.skoda-auto.cz"
BASE_URL_IDENT = "https://identity.vwgroup.io"


class LoginMeta:
    hmac: str
    csrf: str
    relay_state: str

    def __init__(self, dict):
        self.csrf = dict.get("csrf_token")
        self.hmac = dict.get("templateModel", {}).get("hmac")
        self.relay_state = dict.get("templateModel", {}).get("relayState")


class AuthenticationCodes:
    code: str
    token_type: str
    id_token: str

    def __init__(self, dict):
        self.code = dict.get("code")
        self.token_type = dict.get("token_type")
        self.id_token = dict.get("id_token")


class Capability:
    id: str

    def __init__(self, dict):
        self.id = dict.get("id")


class User:
    capabilities: list[Capability]
    country: str
    date_of_birth: str
    email: str
    first_name: str
    last_name: str
    id: str
    nickname: str
    phone: str

    def __init__(self, dict):
        self.capabilities = [Capability(cap) for cap in dict.get("capabilities")]
        self.country = dict.get("country")
        self.date_of_birth = dict.get("dateOfBirth")
        self.email = dict.get("email")
        self.first_name = dict.get("firstName")
        self.last_name = dict.get("lastName")
        self.id = dict.get("id")
        self.nickname = dict.get("nickname")
        self.phone = dict.get("phone")


class Vehicle:
    battery_capacity_kwh: int
    engine_power_kw: int
    engine_type: str
    model: str
    model_year: str
    title: str
    vin: str
    software_version: str

    def __init__(self, dict):
        dict = dict.get("deliveredVehicle")
        self.vin = dict.get("vin")
        self.software_version = dict.get("softwareVersion")

        dict = dict.get("specification")
        self.battery_capacity_kwh = dict.get("battery", {}).get("capacityInKWh")
        self.engine_power_kw = dict.get("engine", {}).get("powerInKW")
        self.engine_type = dict.get("engine", {}).get("type")
        self.model = dict.get("model")
        self.model_year = dict.get("modelYear")
        self.title = dict.get("title")


class Charging:
    remaining_distance_m: int
    battery_percent: int
    charging_power_kw: float
    charge_type: str
    charging_rate_in_km_h: float
    remaining_time_min: str
    state: str
    target_percent: str

    def __init__(self, dict):
        self.target_percent = dict.get("settings", {}).get("targetStateOfChargeInPercent")

        dict = dict.get("status")
        self.remaining_distance_m = dict.get("battery", {}).get("remainingCruisingRangeInMeters")
        self.battery_percent = dict.get("battery", {}).get("stateOfChargeInPercent")
        self.charging_power_kw = dict.get("chargePowerInKw")
        self.charge_type = dict.get("chargeType")
        self.charging_rate_in_km_h = dict.get("chargingRateInKilometersPerHour")
        self.remaining_time_min = dict.get("remainingTimeToFullyChargedInMinutes")
        self.state = dict.get("state")


class VehicleStatus:
    bonnet: str
    doors: str
    trunk: str
    doors_locked: bool
    lights_on: bool
    locked: bool
    windows: str

    def __init__(self, dict):
        self.bonnet = dict.get("detail", {}).get("bonnet")
        self.doors = dict.get("overall", {}).get("doors")
        self.trunk = dict.get("detail", {}).get("trunk")
        self.doors_locked = dict.get("overall", {}).get("doorsLocked")
        self.lights_on = dict.get("overall", {}).get("lights") == "ON"
        self.locked = dict.get("overall", {}).get("locked") == "YES"
        self.windows = dict.get("overall", {}).get("windows")


class AirConditioning:
    window_heating_enabled: bool
    window_heating_front_on: bool
    window_heating_rear_on: bool
    target_temperature_celsius: float
    steering_wheel_position: str
    air_conditioning_on: bool
    charger_connection_state: str
    charger_lock_state: str
    time_to_reach_target_temperature: str

    def __init__(self, dict):
        self.window_heating_enabled = dict.get("windowHeatingEnabled")
        self.window_heating_front_on = dict.get("windowHeatingState", {}).get("front") == "ON"
        self.window_heating_rear_on = dict.get("windowHeatingState", {}).get("rear") == "ON"
        self.target_temperature_celsius = dict.get("targetTemperature", {}).get("temperatureValue")
        self.steering_wheel_position = dict.get("steeringWheelPosition")
        self.air_conditioning_on = dict.get("state") == "ON"
        self.charger_connection_state = dict.get("chargerConnectionState")
        self.charger_lock_state = dict.get("chargerLockState")
        self.time_to_reach_target_temperature = dict.get(
            "estimatedDateTimeToReachTargetTemperature"
        )


class Position:
    city: str
    country: str
    country_code: str
    house_number: str
    street: str
    zip_code: str
    lat: float
    lng: float

    def __init__(self, dict):
        dict = dict.get("positions")[0]
        self.city = dict.get("address", {}).get("city")
        self.country = dict.get("address", {}).get("country")
        self.country_code = dict.get("address", {}).get("countryCode")
        self.house_number = dict.get("address", {}).get("houseNumber")
        self.street = dict.get("address", {}).get("street")
        self.zip_code = dict.get("address", {}).get("zipCode")
        self.lat = dict.get("gpsCoordinates", {}).get("latitude")
        self.lng = dict.get("gpsCoordinates", {}).get("longitude")


class Health:
    mileage_km: int

    def __init__(self, dict):
        self.mileage_km = dict.get("mileageInKm")


def parse_idk_info(html):
    """
    Information such as the CSRF or the hmac will be available in the HTML.

    This method will parse the information from a `<script>` tag in the HTML using BS4.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Regex to extract the information assigned to `window._IDK` from the script tag.
    json_object = re.compile(r"window\._IDK\s=\s((?:\n|.)*?)$")

    dict = None

    # Search through all script tags and find the first one to match the Regex.
    for script in soup.find_all("script"):
        if len(script.contents) != 1:
            continue
        content = script.contents[0].strip()
        result = json_object.search(content)
        if result == None:
            continue

        result = result.group(1)
        # Load the info using YAML, since the syntax used in the script is YAML compatible,
        # but not JSON compatible (missing quotes around field names, trailing commas).
        dict = yaml.safe_load(result)

    return dict


class Client:
    email: str
    password: str
    access_code: str | None
    session: ClientSession

    def __init__(self, email, password, session):
        self.email = email
        self.password = password
        self.session = session

    async def _initial_oidc_authorize(self, session, verifier):
        """
        First step of the login process.

        This calls the route for initial authorization, which will contain the initial SSO information
        such as the CSRF or the HMAC.
        """

        # A SHA256 hash of the random "verifier" string will be transmitted as a challenge.
        # This is part of the OAUTH2 PKCE process. It is described here in detail: https://www.oauth.com/oauth2-servers/pkce/authorization-request/
        verifier_hash = hashlib.sha256(verifier.encode("utf-8")).digest()
        challenge = (
            base64.b64encode(verifier_hash)
            .decode("utf-8")
            .replace("+", "-")
            .replace("/", "_")
            .rstrip("=")
        )

        params = {
            "client_id": CLIENT_ID,
            "nonce": str(uuid.uuid4()),
            "redirect_uri": "myskoda://redirect/login/",
            "response_type": "code id_token",
            # OpenID scopes. Can be found here: https://identity.vwgroup.io/.well-known/openid-configuration
            "scope": "address badge birthdate cars driversLicense dealers email mileage mbb nationalIdentifier openid phone profession profile vin",
            "code_challenge": challenge,
            "code_challenge_method": "s256",
            "prompt": "login",
        }
        async with session.get(f"{BASE_URL_IDENT}/oidc/v1/authorize", params=params) as response:
            dict = parse_idk_info(await response.text())
            return LoginMeta(dict)

    async def _login_identifier(self, session, login_meta):
        """
        Second step in the login process.

        Will post only the email address to the backend. The password will follow in a later request.
        """
        form_data = FormData()
        form_data.add_field("relayState", login_meta.relay_state)
        form_data.add_field("email", self.email)
        form_data.add_field("hmac", login_meta.hmac)
        form_data.add_field("_csrf", login_meta.csrf)

        async with session.post(
            f"{BASE_URL_IDENT}/signin-service/v1/{CLIENT_ID}/login/identifier",
            data=form_data(),
        ) as response:
            dict = parse_idk_info(await response.text())
            return LoginMeta(dict)

    async def _login_authenticate(self, session, login_meta):
        """
        Third step in the login process.

        Post both the email address and the password to the backend.
        This will return a token which can then be used in the skoda services to authenticate.
        """
        form_data = FormData()
        form_data.add_field("relayState", login_meta.relay_state)
        form_data.add_field("email", self.email)
        form_data.add_field("password", self.password)
        form_data.add_field("hmac", login_meta.hmac)
        form_data.add_field("_csrf", login_meta.csrf)

        # The following is a bit hacky:
        # The backend will redirect multiple times after the login was successful.
        # The last redirect will redirect back to the `MySkoda` app in Android, using the `myskoda://` URL prefix.
        # The following loop will follow all redirects until the last redirect to `myskoda://` is encountered.
        # This last URL will contain the token.
        async with session.post(
            f"{BASE_URL_IDENT}/signin-service/v1/{CLIENT_ID}/login/authenticate",
            data=form_data(),
            allow_redirects=False,
        ) as response:
            location = response.headers["Location"]
            while not location.startswith("myskoda://"):
                async with session.get(location, allow_redirects=False) as response:
                    location = response.headers["Location"]
            codes = location.replace("myskoda://redirect/login/#", "")

            # The last redirection starting with `myskoda://` was encountered.
            # The URL will contain the information we need as query parameters, without the leading `?`.
            dict = {}
            for code in codes.split("&"):
                [key, value] = code.split("=")
                dict[key] = value

            return AuthenticationCodes(dict)

    async def _exchange_code(self, session, code, verifier):
        """
        Exchange the ident login code for an auth token from Skoda.

        This will return multiple tokens, such as an access token and a refresh token.
        """
        print(f"_exchange_code code: {code}")
        print(f"_exchange_code verifier: {verifier}")
        json_data = {
            "code": code,
            "redirectUri": "myskoda://redirect/login/",
            "verifier": verifier,
        }

        async with session.post(
            f"{BASE_URL_SKODA}/api/v1/authentication/exchange-authorization-code?tokenType=CONNECT",
            json=json_data,
            allow_redirects=False,
        ) as response:
            login_data = json.loads(await response.text())
            print(f"login_data: {login_data}")
            # login_data["accessToken"]
            # login_data["refreshToken"]
            # login_data["idToken"]
            return login_data["accessToken"]

    async def login(self):
        """
        Perform the full login process.

        Must be called before any other methods on the class can be called.
        """

        # Generate a random string for the OAUTH2 PKCE challenge. (https://www.oauth.com/oauth2-servers/pkce/authorization-request/)
        verifier = "".join(random.choices(string.ascii_uppercase + string.digits, k=16))

        # Call the initial OIDC (OpenID Connect) authorization, giving us the initial SSO information.
        # The full flow is explain a little bit here: https://openid.net/specs/openid-connect-core-1_0.html#ImplicitFlowAuth
        login_meta = await self._initial_oidc_authorize(self.session, verifier)

        # Use the information to login with the email address, which is an extra step before the actual login.
        login_meta = await self._login_identifier(self.session, login_meta)

        # Perform the actual login which will result in a token that can be exchanged for an access token at the Skoda server.
        authentication = await self._login_authenticate(self.session, login_meta)

        # Exchange the token for an access token (JWT format).
        self.access_token = await self._exchange_code(self.session, authentication.code, verifier)

    def _headers(self):
        return {"authorization": f"Bearer {self.access_token}"}

    async def get_user(self):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v1/users", headers=self._headers()
        ) as response:
            return User(await response.json())

    async def get_vehicle(self):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v2/garage/initial-vehicle?connectivityGenerations=MOD3&connectivityGenerations=MOD4",
            headers=self._headers(),
        ) as response:
            j = await response.json()
            print(f"XXXX vehicle response = {j}")
            return Vehicle(await response.json())

    async def get_charging(self, vin):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v1/charging/{vin}", headers=self._headers()
        ) as response:
            return Charging(await response.json())

    async def get_vehicle_status(self, vin):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v2/vehicle-status/{vin}", headers=self._headers()
        ) as response:
            return VehicleStatus(await response.json())

    async def get_air_conditioning(self, vin):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v2/air-conditioning/{vin}", headers=self._headers()
        ) as response:
            return AirConditioning(await response.json())

    async def get_position(self, vin):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v1/maps/positions?vin={vin}", headers=self._headers()
        ) as response:
            return Position(await response.json())

    async def get_health(self, vin):
        async with self.session.get(
            f"{BASE_URL_SKODA}/api/v1/vehicle-health-report/warning-lights/{vin}",
            headers=self._headers(),
        ) as response:
            return Health(await response.json())

    async def stop_air_conditioning(self, vin):
        async with self.session.post(
            f"{BASE_URL_SKODA}/api/v2/air_conditioning/{vin}/stop",
            headers=self._headers(),
        ) as response:
            await response.text()

    async def start_air_conditioning(self, vin, temperature):
        json_data = {
            "heaterSource": "ELECTRIC",
            "targetTemperature": {
                "temperatureValue": temperature,
                "unitInCar": "CELSIUS",
            },
        }
        async with self.session.post(
            f"{BASE_URL_SKODA}/api/v2/air_conditioning/{vin}/start",
            headers=self._headers(),
            json=json_data,
        ) as response:
            await response.text()

    async def start_window_heating(self, vin):
        async with self.session.post(
            f"{BASE_URL_SKODA}/api/v2/air_conditioning/{vin}/start-window-heating",
            headers=self._headers(),
        ) as response:
            await response.text()

    async def stop_window_heating(self, vin):
        async with self.session.post(
            f"{BASE_URL_SKODA}/api/v2/air_conditioning/{vin}/stop-window-heating",
            headers=self._headers(),
        ) as response:
            await response.text()

    async def set_maximum_charging_current(self, vin):
        json_data = {"chargingCurrent": "MAXIMUM"}
        async with self.session.put(
            f"{BASE_URL_SKODA}/api/v1/charging/{vin}/set-charging-current",
            headers=self._headers(),
            json=json_data,
        ) as response:
            await response.text()

    async def set_reduced_charging_current(self, vin):
        json_data = {"chargingCurrent": "REDUCED"}
        async with self.session.put(
            f"{BASE_URL_SKODA}/api/v1/charging/{vin}/set-charging-current",
            headers=self._headers(),
            json=json_data,
        ) as response:
            await response.text()


async def main():
    async with ClientSession() as session:
        client = Client(sys.argv[1], sys.argv[2], session)
        await client.login()
        user = await client.get_user()
        vehicle = await client.get_vehicle()
        # vehicle_status = await client.get_vehicle_status(vehicle.vin)
        # charging = await client.get_charging(vehicle.vin)
        # air_conditioning = await client.get_air_conditioning(vehicle.vin)
        # position = await client.get_position(vehicle.vin)
        # health = await client.get_health(vehicle.vin)

        # print(f"User is {user.first_name} {user.last_name}")
        # print(
        #     f"Vehicle {vehicle.title} with {vehicle.battery_capacity_kwh}kWh capacity and {vehicle.engine_power_kw}kW engine"
        # )
        # print(
        #     f"Vehicle doors locked: {vehicle_status.doors_locked}, windows open: {vehicle_status.windows}"
        # )
        # print(
        #     f"Battery at {charging.battery_percent}% with a range of {charging.remaining_distance_m}m"
        # )
        # print(
        #     f"Air conditioning is {air_conditioning.air_conditioning_on}, target temperature is {air_conditioning.target_temperature_celsius}°C"
        # )
        # print(
        #     f"Charger state: {air_conditioning.charger_connection_state} and locked: {air_conditioning.charger_lock_state}"
        # )
        # print(
        #     f"Vehicle is located at {position.street} {position.house_number}, {position.zip_code} {position.city} - {position.country}"
        # )
        # print(f"GPS {position.lat}/{position.lng}")
        # print(f"Mileage: {health.mileage_km}km")


if __name__ == "__main__":
    asyncio.run(main())
