#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Communicate with Skoda Connect."""
"""Fork of https://github.com/robinostlund/volkswagencarnet where it was modified to support also Skoda Connect"""
import re
import time
import logging
import asyncio
import hashlib

from sys import version_info, argv
from datetime import timedelta, datetime, timezone
from urllib.parse import urlsplit, urljoin, parse_qs, urlparse
from json import dumps as to_json
from collections import OrderedDict
import aiohttp
from bs4 import BeautifulSoup
from base64 import b64decode, b64encode
from skodaconnect.utilities import find_path, is_valid_path, read_config, json_loads
from skodaconnect.vehicle import Vehicle

from aiohttp import ClientSession, ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST

version_info >= (3, 0) or exit('Python 3 required')

_LOGGER = logging.getLogger(__name__)

TIMEOUT = timedelta(seconds=30)

HEADERS_SESSION = {
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    "X-Client-Id": '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com',
    "X-App-Version": '3.2.6',
    "X-App-Name": 'cz.skodaauto.connect',
    "Accept-charset": "UTF-8",
    #"Accept": "application/json,*/*",
    "Accept": "application/json",
    'User-Agent': 'okhttp/3.7.0'
}

HEADERS_AUTH = {
    'Connection': 'keep-alive',
    'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,\
        image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
    'Content-Type': 'application/x-www-form-urlencoded',
    'User-Agent': 'OneConnect/200605002 CFNetwork/1128 Darwin/19.6.0'
}

BASE_SESSION = 'https://msg.volkswagen.de'
BASE_AUTH = 'https://identity.vwgroup.io'
CLIENT_ID = '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com'

class Connection:
    """ Connection to Skoda connect """

    def __init__(self, session, username, password, guest_lang='en'):
        """ Initialize """
        self._session = session
        self._session_headers = HEADERS_SESSION.copy()
        self._session_base = BASE_SESSION
        self._session_auth_headers = HEADERS_AUTH.copy()
        self._session_auth_base = BASE_AUTH
        self._session_guest_language_id = guest_lang

        self._session_auth_ref_url = BASE_SESSION
        self._session_spin_ref_url = BASE_SESSION
        self._session_logged_in = False
        self._session_first_update = False
        self._session_auth_username = username
        self._session_auth_password = password

        self._vin = ""
        self._vehicles = []

        _LOGGER.debug('Using service <%s>', self._session_base)

        self._jarCookie = ""
        self._state = {}

    def _clear_cookies(self):
        self._session._cookie_jar._cookies.clear()

    async def _login(self):
        """ Reset session in case we would like to login again """
        self._session_headers = HEADERS_SESSION.copy()
        self._session_auth_headers = HEADERS_AUTH.copy()

        def extract_csrf(req):
            return re.compile('<meta name="_csrf" content="([^"]*)"/>').search(req).group(1)

        def extract_guest_language_id(req):
            return req.split('_')[1].lower()

        def getNonce():
            ts = "%d" % (time.time())
            sha256 = hashlib.sha256()
            sha256.update(ts.encode())
            return (b64encode(sha256.digest()).decode("utf-8")[:-1])

        try:
            # remove cookies from session as we are doing a new login
            self._clear_cookies()

            # Request landing page and get auth URL:
            req = await self._session.get(
                url="https://identity.vwgroup.io/.well-known/openid-configuration"
            )
            if req.status != 200:
                return ""
            response_data =  await req.json()
            authorizationEndpoint = response_data["authorization_endpoint"]
            authissuer = response_data["issuer"]

            # Get authorization
            # https://identity.vwgroup.io/oidc/v1/authorize?nonce=yVOPHxDmksgkMo1HDUp6IIeGs9HvWSSWbkhPcxKTGNU&response_type=code id_token token&scope=openid mbb&ui_locales=de&redirect_uri=skodaconnect://oidc.login/&client_id=7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com             
            req = await self._session.get(
                url=authorizationEndpoint+'?nonce='+getNonce()+'&response_type=code id_token token&scope=openid mbb&ui_locales=de&redirect_uri=skodaconnect://oidc.login/&client_id='+CLIENT_ID,
                headers=self._session_auth_headers
            )
            if req.status != 200:
                return ""
            response_data = await req.text()
            responseSoup = BeautifulSoup(response_data, 'html.parser')
            mailform = dict([(t["name"],t["value"]) for t in responseSoup.find('form', id='emailPasswordForm').find_all("input", type="hidden")])
            mailform["email"] = self._session_auth_username
            pe_url = authissuer+responseSoup.find('form', id='emailPasswordForm').get('action')

            # POST email
            # https://identity.vwgroup.io/signin-service/v1/xxx@apps_vw-dilab_com/login/identifier
            self._session_auth_headers['Referer'] = authorizationEndpoint
            self._session_auth_headers['Origin'] = authissuer
            req = await self._session.post(
                url=pe_url,
                headers=self._session_auth_headers,
                data = mailform
            )
            if req.status != 200:
                return ""
            response_data = await req.text()
            responseSoup = BeautifulSoup(response_data, 'html.parser')
            pwform = dict([(t["name"],t["value"]) for t in responseSoup.find('form', id='credentialsForm').find_all("input", type="hidden")])
            pwform["password"] = self._session_auth_password
            pw_url = authissuer+responseSoup.find('form', id='credentialsForm').get('action')

            # POST password
            # https://identity.vwgroup.io/signin-service/v1/xxx@apps_vw-dilab_com/login/authenticate
            self._session_auth_headers['Referer'] = pe_url
            self._session_auth_headers['Origin'] = authissuer
            excepted = False

            req = await self._session.post(
                url=pw_url,
                headers=self._session_auth_headers,
                data = pwform,
                allow_redirects=False
            )
            if req.status != 302:
                return ""

            # https://identity.vwgroup.io/oidc/v1/oauth/sso?clientId=xxx@apps_vw-dilab_com&relayState=xxx&userId=xxxGUID&HMAC=xxxx
            ref_url_1 = req.headers.get("location")
            req = await self._session.get(ref_url_1, allow_redirects=False, headers=self._session_auth_headers)
            if req.status != 302:
                return ""

            # https://identity.vwgroup.io/oidc/v1/oauth/client/callback?clientId=xxx@apps_vw-dilab_com&relayState=xxx&userId=xxxGUID&HMAC=xxx
            ref_url_3 = req.headers.get('location')
            req = await self._session.get(
                url=ref_url_3,
                allow_redirects=False,
                headers=self._session_auth_headers
            )
            if req.status != 302:
                return ""

            # skodaconnect://oidc.login/#code=xxx&access_token=xxx&expires_in=3600&token_type=bearer&id_token=xxx 
            skodaURL = req.headers.get('location')

            # Exchange Auth code for JWT tokens
            # https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode
            jwtauth_code = parse_qs(urlparse(skodaURL).fragment).get('code')[0]
            jwtaccess_token = parse_qs(urlparse(skodaURL).fragment).get('access_token')[0]
            jwtid_token = parse_qs(urlparse(skodaURL).fragment).get('id_token')[0]

            tokenBody = {
                "auth_code": jwtauth_code,
                "id_token":  jwtid_token,
                "brand": "skoda"
            }
            tokenURL = "https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode"
            req = await self._session.post(
                url=tokenURL,
                headers=self._session_auth_headers,
                data = tokenBody,
                allow_redirects=False
            )
            if req.status != 200:
                return ""

            vwtok = await req.json()
            atoken = vwtok["access_token"]
            rtoken = vwtok["refresh_token"]

            # Get VW API tokens
            # https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token
            tokenBody2 =  {
                "grant_type": "id_token",
                "token": jwtid_token,
                "scope": "sc2:fal"
            }
            req = await self._session.post(
                    url='https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token',
                    headers= {
                        "User-Agent": "okhttp/3.7.0",
                        "X-App-Version": "3.2.6",
                        "X-App-Name": "cz.skodaauto.connect",
                        "X-Client-Id": "28cd30c6-dee7-4529-a0e6-b1e07ff90b79",
                        "Host": "mbboauth-1d.prd.ece.vwg-connect.com",
                    },
                    #self._session_headers,
                    data = tokenBody2,
                    allow_redirects=False
                )
            if req.status > 400:
                _LOGGER.debug("Tokens wrong")
                return ""
            else:
                _LOGGER.debug("Tokens OK")
            rtokens = await req.json()
            atoken = rtokens["access_token"]
            rtoken = rtokens["refresh_token"]

            # Update headers for requests
            self._session_headers['Authorization'] = "Bearer " + atoken
            self._session_logged_in = True
            return True

        except Exception as error:
            _LOGGER.error('Failed to login to Skoda Connect, %s' % error)
            self._session_logged_in = False
            return False

    async def _request(self, method, url, **kwargs):
        """Perform a query to the Skoda Connect"""
        # try:
        _LOGGER.debug("Request for %s", url)

        async with self._session.request(
            method,
            url,
            headers=self._session_headers,
            timeout=ClientTimeout(total=TIMEOUT.seconds),
            cookies=self._jarCookie,
            **kwargs
        ) as response:
            response.raise_for_status()

            if self._jarCookie != "":
                self._jarCookie.update(response.cookies)
            else:
                self._jarCookie = response.cookies

            try:
                _LOGGER.debug("Response headers: %s" % response.headers)
                if response.status == 204:
                    res = {'status_code': response.status}
                elif response.status >= 200 or response.status <= 300:
                    res = await response.json(loads=json_loads)
                else:
                    res = {}
                    _LOGGER.debug(f'Not success status code [{response.status}] response: {response}')
                if "X-RateLimit-Remaining" in response.headers:
                    res['rate_limit_remaining'] = response.headers.get("X-RateLimit-Remaining", "")
            except:
                res = {}
                _LOGGER.debug(f'Something went wrong [{response.status}] response: {response}')
                return res

            _LOGGER.debug(f'Received [{response.status}] response: {res}')
            return res
        # except Exception as error:
        #     _LOGGER.warning(
        #         "Failure when communcating with the server: %s", error
        #     )
        #     raise

    async def _logout(self):
        await self.post('-/logout/revoke')
        # remove cookies from session as we have logged out
        self._clear_cookies()

    def _make_url(self, ref, vin=''):
        replacedUrl = re.sub("\$vin", vin, ref)
        if ("://" in replacedUrl):
            #already server contained in URL
            return replacedUrl
        elif "rolesrights" in replacedUrl:
            return urljoin(self._session_spin_ref_url, replacedUrl)
        else:
            return urljoin(self._session_auth_ref_url, replacedUrl)

    async def get(self, url, vin=''):
        """Perform a get query to the online service."""
        return await self._request(METH_GET, self._make_url(url, vin))

    async def post(self, url, vin='', **data):
        """Perform a post query to the online service."""
        if data:
            return await self._request(METH_POST, self._make_url(url, vin), **data)
        else:
            return await self._request(METH_POST, self._make_url(url, vin))

    async def update(self):
        """Update status."""
        try:
            if self._session_first_update:
                if not await self.validate_login:
                    _LOGGER.info('Session expired, creating new login session to skoda connect.')
                    await self._login()
            else:
                self._session_first_update = True

            # fetch vehicles
            _LOGGER.debug('Fetching vehicles')

            # get vehicles
            if "Content-Type" in self._session_headers:
                del self._session_headers["Content-Type"]
            loaded_vehicles = await self.get(
                url='https://msg.volkswagen.de/fs-car/usermanagement/users/v1/skoda/CZ/vehicles'
            )
            _LOGGER.debug('URL loaded')

            # update vehicles
            if loaded_vehicles.get('userVehicles', {}).get('vehicle', []):
                _LOGGER.debug('Vehicle JSON string exists')
                for vehicle in loaded_vehicles.get('userVehicles').get('vehicle'):
                    vehicle_url = vehicle
                    _LOGGER.debug('Vehicle_URL %s', vehicle_url)
                    self._state.update({vehicle_url: dict()})
                    self._vehicles.append(Vehicle(self, vehicle_url))
                    # if vehicle_url not in self._state:
                    #     _LOGGER.debug('Vehicle_URL not in states, adding')
                    #     self._state.update({vehicle_url: dict()})
                    # else:
                    #     _LOGGER.debug('Vehicle_URL in states, updating')
                    #     for key, value in vehicle.items():
                    #         self._state[vehicle_url].update({key: value})

            _LOGGER.debug('Going to call vehicle updates')
            # get vehicle data
            for vehicle in self.vehicles:
                # update data in all vehicles
                await vehicle.update()
            return True
        except (IOError, OSError, LookupError) as error:
            _LOGGER.warning(f'Could not update information from skoda connect: {error}')

    async def update_vehicle(self, vehicle):
        url = vehicle._url
        self._vin=url
        _LOGGER.debug(f'Updating vehicle status {vehicle.vin}')

        try:
            await self.getHomeRegion(url)
        except Exception as err:
            _LOGGER.debug(f'Cannot get homeregion, error: {err}')

        # Car Info
        #https://msg.volkswagen.de/fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata
        try:            
            response = await self.get('fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata', vin=url)
            if response.get('carportData', {}) :
                self._state[url].update(
                    {'carportData': response.get('carportData', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch carportData: {response}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch carportData, error: {err}')

        # Position data
        #https://msg.volkswagen.de/fs-car/bs/cf/v1/skoda/CZ/vehicles/$vin/position
        try:
            response = await self.get('fs-car/bs/cf/v1/skoda/CZ/vehicles/$vin/position', vin=url)
            if response.get('findCarResponse', {}) :
                self._state[url].update(
                    {'findCarResponse': response.get('findCarResponse', {})}
                )
                self._state[url].update({ 'isMoving': False })
            elif response.get('status_code', 0) == 204:
                _LOGGER.debug(f'Seems car is moving, HTTP 204 received from position')
                self._state[url].update({ 'isMoving': True })
                self._requests_remaining = 15
            else:
                _LOGGER.debug(f'Could not fetch position: {response}')
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 204):
                _LOGGER.debug(f'Seems car is moving, HTTP 204 received from position')
                self._state[url].update({ 'isMoving': True })
                self._requests_remaining = 15
            else:
                _LOGGER.warning(f'Could not fetch position (ClientResponseError), error: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch position, error: {err}')

        # Stored car data
        #https://msg.volkswagen.de/fs-car/bs/vsr/v1/skoda/CZ/vehicles/$vin/status
        try:
            response = await self.get('fs-car/bs/vsr/v1/skoda/CZ/vehicles/$vin/status', vin=url)
            if response.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})[0].get('field', {})[0] :
                self._state[url].update(
                    {'StoredVehicleDataResponse': response.get('StoredVehicleDataResponse', {})}
                )
                self._state[url].update(
                    {'StoredVehicleDataResponseParsed' :  dict([(e["id"],e if "value" in e else "") for f in [s["field"] for s in response["StoredVehicleDataResponse"]["vehicleData"]["data"]] for e in f]) }
                )
            else:
                _LOGGER.debug(f'Could not fetch StoredVehicleDataResponse: {response}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch StoredVehicleDataResponse, error: {err}')

        # TRIP DATA
        #https://msg.volkswagen.de/fs-car/bs/tripstatistics/v1/skoda/CZ/vehicles/TMBJJ7NS3L8500308/tripdata/shortTerm?newest
        # -or- shortTerm?type=list -or- longTerm?type=list
        try:
            response = await self.get('fs-car/bs/tripstatistics/v1/skoda/CZ/vehicles/$vin/tripdata/shortTerm?newest', vin=url)            
            if response.get('tripData', {}):
                self._state[url].update(
                    {'tripstatistics': response.get('tripData', {})}
                )                                
            else:
                _LOGGER.debug(f'Could not fetch tripstatistics: {response}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch tripstatistics, error: {err}')

        # CLIMATISATION DATA
        #https://msg.volkswagen.de/fs-car/bs/climatisation/v1/skoda/CZ/vehicles/<VIN>/climater
        try:
            response = await self.get('fs-car/bs/climatisation/v1/skoda/CZ/vehicles/$vin/climater', vin=url)
            if response.get('climater', {}):
                self._state[url].update(
                    {'climater': response.get('climater', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch climatisation: {response}')
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403):
                _LOGGER.debug(f'Could not fetch climatisation, error 403 (not supported on car?), error: {err}')
            else:
                _LOGGER.warning(f'Could not fetch climatisation (ClientResponseError), error: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch climatisation, error: {err}')

        # CHARGING DATA
        #https://msg.volkswagen.de/fs-car/bs/batterycharge/v1/skoda/CZ/vehicles/<VIN>/charger
        try:
            response = await self.get('fs-car/bs/batterycharge/v1/skoda/CZ/vehicles/$vin/charger', vin=url)
            if response.get('charger', {}):
                self._state[url].update(
                    {'charger': response.get('charger', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch charger: {response}')
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403):
                _LOGGER.debug(f'Could not fetch charger, error 403 (not supported on car?), error: {err}')
            else:
                _LOGGER.warning(f'Could not fetch charger (ClientResponseError), error: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch charger, error: {err}')

        # Pre-heater status (auxiliary heating)
        # https://msg.volkswagen.de/fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/status
        try:
            
            response = await self.get('fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/status', vin=url)
            if response.get('statusResponse', {}) :
                self._state[url].update(
                    {'heating': response.get('statusResponse', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch pre-heating: {response}')
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch pre-heating, error 403/502 (not supported on car?), error: {err}')
            else:
                _LOGGER.warning(f'Could not fetch pre-heating (ClientResponseError), error: {err}')        
        except Exception as err:
            _LOGGER.warning(f'Could not fetch pre-heating, error: {err}')
    
    async def getHomeRegion(self, vin):
        _LOGGER.debug("Getting homeregion for %s" % vin)
        try:
            response = await self.get('https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/$vin/homeRegion', vin)
            self._session_auth_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0].replace("mal-", "fal-") if response['homeRegion']['baseUri']['content'] != "https://mal-1a.prd.ece.vwg-connect.com/api" else "https://msg.volkswagen.de"
            self._session_spin_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0] 
        except:
            _LOGGER.debug(f'Retrying homeregion for %s' % vin)
            response = await self.get('https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/$vin/homeRegion', vin)
            self._session_auth_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0].replace("mal-", "fal-") if response['homeRegion']['baseUri']['content'] != "https://mal-1a.prd.ece.vwg-connect.com/api" else "https://msg.volkswagen.de"
            self._session_spin_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0] 

    def vehicle(self, vin):
        """Return vehicle for given vin."""
        return next(
            (
                vehicle
                for vehicle in self.vehicles
                if vehicle.unique_id == vin.lower()
            ), None
        )

    @property
    def vehicles(self):
        """Return vehicle state."""
        #return (Vehicle(self, url) for url in self._state)
        return self._vehicles

    def vehicle_attrs(self, vehicle_url):
        return self._state.get(vehicle_url)

    @property
    async def validate_login(self):
        try:
            response = await self.get('fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata', vin=self._vin)            
            if response.get('carportData', {}) :            
                return True
            else:
                return False
        except (IOError, OSError) as error:
            _LOGGER.warning('Could not validate login: %s', error)
            return False
        except (aiohttp.client_exceptions.ClientResponseError) as error:
            if (error.status == 401):
                _LOGGER.info(f'Could not validate login - unauthorized, need to login again')
                return False
        except Exception as error:
            _LOGGER.warning(f'Could not validate login2: {error}')
            return False

    @property
    def logged_in(self):
        return self._session_logged_in

async def main():
    """Main method."""
    if "-v" in argv:
        logging.basicConfig(level=logging.INFO)
    elif "-vv" in argv:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.ERROR)   

    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        connection = Connection(session, **read_config())
        if await connection._login():
            if await connection.update():
                for vehicle in connection.vehicles:
                    print(f'Vehicle id: {vehicle}')
                    print('Supported sensors:')
                    #await vehicle.lock_car("1234")
                    #await vehicle.stop_combustion_engine_heating()
                    for instrument in vehicle.dashboard().instruments:
                        print(f' - {instrument.name} (domain:{instrument.component}) - {instrument.str_state}')
                    
                    #print(vehicle.last_connected)
                    #print(vehicle.service_inspection)
                    #print(vehicle.position)
                    #print(await vehicle.requestSecToken("1234"))
                    #ts = vehicle.position.get('timestamp')
                    #print(ts.astimezone(tz=None))
            #await connection._logout()
                    #await vehicle.start_combustion_engine_heating("1234", 20)
                    #await vehicle.update()
                    #await vehicle.stop_combustion_engine_heating()
            

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # loop.run(main())
    loop.run_until_complete(main())
