#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Communicate with Skoda Connect."""
"""Fork of https://github.com/robinostlund/volkswagencarnet where it was modified to support also Skoda Connect"""
"""Modified to utilize Skoda App API instead of Web API"""
import re
import time
import logging
import asyncio
import hashlib
import jwt

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

from .const import (
    HEADERS_SESSION
)

version_info >= (3, 0) or exit('Python 3 required')

_LOGGER = logging.getLogger(__name__)

TIMEOUT = timedelta(seconds=30)

HEADERS_SESSION = {
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    "X-Client-Id": '28cd30c6-dee7-4529-a0e6-b1e07ff90b79',
    "X-App-Version": '3.2.6',
    "X-App-Name": 'cz.skodaauto.connect',
    "Accept-charset": "UTF-8",
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

  # Init connection class
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
        self._session_tokens = {}

        self._vin = ""
        self._vehicles = []

        _LOGGER.debug('Using service <%s>', self._session_base)

        self._jarCookie = ""
        self._state = {}

    def _clear_cookies(self):
        self._session._cookie_jar._cookies.clear()

  # API Login
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
            # Remove cookies from session as we are doing a new login
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
             params = {
                "nonce": getNonce(),
                "response_type":  "code id_token token",
                "scope": "openid profile address cars email birthdate badge mbb phone driversLicense dealers",
                "redirect_uri": "skodaconnect://oidc.login/",
                "client_id": CLIENT_ID
            }
            req = await self._session.get(
                url=authorizationEndpoint,
                headers=self._session_auth_headers,
                params=params
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
             # Follow all redirects until we get redirected back to "our app"
            try:
                maxDepth = 10
                ref = req.headers['Location']
                while not ref.startswith("skodaconnect://oidc.login/"):
                    response = await self._session.get(
                        url=ref,
                        headers=self._session_auth_headers,
                        allow_redirects=False
                    )
                    ref = response.headers['Location']
                    # Set a max limit on requests to prevent forever loop
                    maxDepth -= 1
                    if maxDepth == 0:
                        _LOGGER.warning("Should have gotten a token by now.")
                        return False
            except:
                # If we get excepted it should be because we can't redirect to the skodaconnect:// URL
                _LOGGER.debug("Got code: %s" % ref)
                pass

            # Extract code and tokens
            jwt_auth_code = parse_qs(urlparse(ref).fragment).get('code')[0]
            jwt_access_token = parse_qs(urlparse(ref).fragment).get('access_token')[0]
            jwt_id_token = parse_qs(urlparse(ref).fragment).get('id_token')[0]

            # Exchange Auth code for Skoda tokens
            tokenBody = {
                'auth_code': jwt_auth_code,
                'id_token':  jwt_id_token,
                'brand': 'skoda'
            }
            tokenURL = 'https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode'
            req = await self._session.post(
                url=tokenURL,
                headers=self._session_auth_headers,
                data = tokenBody,
                allow_redirects=False
            )
            if req.status != 200:
                return ""
            # Save tokens as "identity", this is tokens representing the user
            self._session_tokens['identity'] = await req.json()
            if not await self.verify_tokens(self._session_tokens['identity']['id_token'], 'identity'):
                _LOGGER.warning('Identity token could not be verified!')
            else:
                _LOGGER.debug('Identity token verified OK.')

            # Get VW Group API tokens
            # https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token
            tokenBody2 =  {
                'grant_type': 'id_token',
                'token': self._session_tokens['identity']['id_token'],
                'scope': 'sc2:fal'
            }
            req = await self._session.post(
                    url='https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token',
                    headers= {
                        'User-Agent': 'okhttp/3.7.0',
                        'X-App-Version': '3.2.6',
                        'X-App-Name': 'cz.skodaauto.connect',
                        'X-Client-Id': '28cd30c6-dee7-4529-a0e6-b1e07ff90b79',
                        'Host': 'mbboauth-1d.prd.ece.vwg-connect.com',
                    },
                    data = tokenBody2,
                    allow_redirects=False
                )
            if req.status > 400:
                _LOGGER.debug("Tokens wrong")
                return ""
            else:
                # Save tokens as "vwg", use theese for get/posts to VW Group API
                self._session_tokens['vwg'] = await req.json()
                if not await self.verify_tokens(self._session_tokens['vwg']['access_token'], 'vwg'):
                    _LOGGER.warning('VWG token could not be verified!')
                else:
                    _LOGGER.debug("VWG tokens OK.")

            # Update headers for requests, defaults to using VWG token
            self._session_headers['Authorization'] = 'Bearer ' + self._session_tokens['vwg']['access_token']
            self._session_logged_in = True
            return True

        except Exception as error:
            _LOGGER.error('Failed to login to Skoda Connect, %s' % error)
            self._session_logged_in = False
            return False

  # HTTP methods to API
    async def _request(self, method, url, **kwargs):
        """Perform a query to the Skoda Connect service"""
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

            # Update cookie jar
            if self._jarCookie != "":
                self._jarCookie.update(response.cookies)
            else:
                self._jarCookie = response.cookies

            try:
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

    async def get(self, url, vin=''):
        """Perform a get query to the online service."""
        return await self._request(METH_GET, self._make_url(url, vin))

    async def post(self, url, vin='', **data):
        """Perform a post query to the online service."""
        if data:
            return await self._request(METH_POST, self._make_url(url, vin), **data)
        else:
            return await self._request(METH_POST, self._make_url(url, vin))

  # Construct URL from request, home region and variables
    def _make_url(self, ref, vin=''):
        replacedUrl = re.sub("\$vin", vin, ref)
        if ("://" in replacedUrl):
            #already server contained in URL
            return replacedUrl
        elif "rolesrights" in replacedUrl:
            return urljoin(self._session_spin_ref_url, replacedUrl)
        else:
            return urljoin(self._session_auth_ref_url, replacedUrl)

  # Change active access token
    async def set_token(self, type):
        """Switch between tokens."""
        self._session_headers['Authorization'] = 'Bearer ' + self._session_tokens[type]['access_token']
        return

  # Update functions
    async def update(self):
        """Update status."""
        try:
            if not await self.validate_tokens:
                _LOGGER.info('Session has expired. Initiating new login to Skoda Connect.')
                await self._login()

            if not self._session_first_update:
                # Get vehicles
                _LOGGER.debug('Fetching vehicles')
                await self.set_token('vwg')
                if "Content-Type" in self._session_headers:
                    del self._session_headers["Content-Type"]
                loaded_vehicles = await self.get(
                    url='https://msg.volkswagen.de/fs-car/usermanagement/users/v1/skoda/CZ/vehicles'
                )
                _LOGGER.debug('URL loaded')

            # Update list of vehicles
            if loaded_vehicles.get('userVehicles', {}).get('vehicle', []):
                _LOGGER.debug('Vehicle JSON string exists')
                for vehicle in loaded_vehicles.get('userVehicles').get('vehicle'):
                    vehicle_url = vehicle
                    self._state.update({vehicle_url: dict()})
                    self._vehicles.append(Vehicle(self, vehicle_url))
            self._session_first_update = True

            _LOGGER.debug('Going to call vehicle updates')
            # Get VIN numbers and update data for each
            for vehicle in self.vehicles:
                # Wait for data update
                await vehicle.update()
            return True
        except (IOError, OSError, LookupError) as error:
            _LOGGER.warning(f'Could not update information from skoda connect: {error}')

    async def update_vehicle(self, vehicle):
        """Update data from VWG servers for given vehicle."""
        url = vehicle._url
        self._vin=url

        if not self._session_logged_in:
            await self._login()

        _LOGGER.debug(f'Updating vehicle status {vehicle.vin}')

        try:
            await self.getHomeRegion(url)
        except Exception as err:
            _LOGGER.debug(f'Cannot get homeregion, error: {err}')

        # Request all car info and wait for all to finish
        await asyncio.gather(
            self.getRealCarData(url),
            self.getCarportData(url),
            self.getPosition(url),
            self.getVehicleStatusData(url),
            self.getTripStatistics(url),
            self.getTimers(url),
            self.getClimater(url),
            self.getCharger(url),
            self.getPreHeater(url),
            return_exceptions=True
        )

 #### Data collect functions ####
    async def getHomeRegion(self, vin):
        _LOGGER.debug("Getting homeregion for %s" % vin)
        try:
            await self.set_token('vwg')
            response = await self.get('https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/$vin/homeRegion', vin)
            self._session_auth_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0].replace("mal-", "fal-") if response['homeRegion']['baseUri']['content'] != "https://mal-1a.prd.ece.vwg-connect.com/api" else "https://msg.volkswagen.de"
            self._session_spin_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0] 
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch homeregion, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
        except:
            _LOGGER.debug(f'Retrying homeregion for %s' % vin)
            response = await self.get('https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/$vin/homeRegion', vin)
            self._session_auth_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0].replace("mal-", "fal-") if response['homeRegion']['baseUri']['content'] != "https://mal-1a.prd.ece.vwg-connect.com/api" else "https://msg.volkswagen.de"
            self._session_spin_ref_url = response['homeRegion']['baseUri']['content'].split("/api")[0] 

    async def getRealCarData(self, vin):
        """Get car information from customer profile, VIN, nickname, etc."""
        try:
            atoken = self._session_tokens['identity']['access_token']
            sub = jwt.decode(atoken, verify=False).get('sub', None)
            await self.set_token('identity')
            response = await self.get(
                'https://customer-profile.apps.emea.vwapps.io/v1/customers/{subject}/realCarData'.format(subject=sub)
            )
            if response.get('realCars', {}):
                carData = {}
                carData = next(item for item in response.get('realCars', []) if item['vehicleIdentificationNumber'] == vin)
                self._state[vin].update(
                    {'carData': carData}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch realCarData: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch realcar data, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch realCarData, error: {err}')
            return False

    async def getCarportData(self, vin):
        """Get carport data for vehicle, model, model year etc."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata',
                vin=vin
            )
            if response.get('carportData', {}) :
                self._state[vin].update(
                    {'carportData': response.get('carportData', {})}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch carportData: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch carport data, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch carportData, error: {err}')
            return False

    async def getVehicleStatusData(self, vin):
        """Get stored vehicle data response."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/vsr/v1/skoda/CZ/vehicles/$vin/status', 
                vin=vin
            )
            if response.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})[0].get('field', {})[0] :
                self._state[vin].update(
                    {'StoredVehicleDataResponse': response.get('StoredVehicleDataResponse', {})}
                )
                self._state[vin].update(
                    {'StoredVehicleDataResponseParsed' :  dict([(e["id"],e if "value" in e else "") for f in [s["field"] for s in response["StoredVehicleDataResponse"]["vehicleData"]["data"]] for e in f]) }
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch StoredVehicleDataResponse: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch vehicle status report, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch StoredVehicleDataResponse, error: {err}')
            return False

    async def getTripStatistics(self, vin):
        """Get short term trip statistics."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/tripstatistics/v1/skoda/CZ/vehicles/$vin/tripdata/shortTerm?newest',
                vin=vin
            )
            if response.get('tripData', {}):
                self._state[vin].update(
                    {'tripstatistics': response.get('tripData', {})}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch trip statistics: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch trip statistics, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch trip statistics, error: {err}')
            return False

    async def getPosition(self, vin):
        """Get position data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/cf/v1/skoda/CZ/vehicles/$vin/position', 
                vin=vin
            )
            if response.get('findCarResponse', {}) :
                self._state[vin].update(
                    {'findCarResponse': response.get('findCarResponse', {})}
                )
                self._state[vin].update({ 'isMoving': False })
                #self._state[vin].pop('rate_limit_remaining')
                return True
            elif response.get('status_code', 0) == 204:
                _LOGGER.debug(f'Seems car is moving, HTTP 204 received from position')
                self._state[vin].update({ 'isMoving': True })
                self._state[vin].update({ 'rate_limit_remaining': 15 })
                return True
            else:
                _LOGGER.debug(f'Could not fetch position: {response}')
                #self._state[vin].pop('rate_limit_remaining')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            #self._state[vin].pop('rate_limit_remaining')
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch position, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif (err.status == 204):
                _LOGGER.debug(f'Seems car is moving, HTTP 204 received from position')
                self._state[vin].update({ 'isMoving': True })
                self._state[vin].update({ 'rate_limit_remaining': 15 })
                return True
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
            else:
                _LOGGER.warning(f'Could not fetch position (ClientResponseError), error: {err}')
            return False
        except Exception as err:
            _LOGGER.warning(f'Could not fetch position, error: {err}')
            return False

    async def getTimers(self, vin):
        """Get departure timers."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/departuretimer/v1/skoda/CZ/vehicles/$vin/timer', 
                vin=vin
            )
            if response.get('timer', {}):
                self._state[vin].update(
                    {'timers': response.get('timer', {})}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch timers: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch timers, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
        except Exception as err:
            _LOGGER.warning(f'Could not fetch timers, error: {err}')
            return False

    async def getClimater(self, vin):
        """Get climatisation data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/climatisation/v1/skoda/CZ/vehicles/$vin/climater',
                vin=vin
            )
            if response.get('climater', {}):
                self._state[vin].update(
                    {'climater': response.get('climater', {})}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch climatisation: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch climatisation, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
            else:
                _LOGGER.warning(f'Could not fetch climatisation (ClientResponseError), error: {err}')
            return False
        except Exception as err:
            _LOGGER.warning(f'Could not fetch climatisation, error: {err}')
            return False

    async def getCharger(self, vin):
        """Get charger data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/batterycharge/v1/skoda/CZ/vehicles/$vin/charger', 
                vin=vin
            )
            if response.get('charger', {}):
                self._state[vin].update(
                    {'charger': response.get('charger', {})}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch charger: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch charger, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
            else:
                _LOGGER.warning(f'Could not fetch charger (ClientResponseError), error: {err}')
            return False
        except Exception as err:
            _LOGGER.warning(f'Could not fetch charger, error: {err}')
            return False

    async def getPreHeater(self, vin):
        """Get aux heater data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                'fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/status', 
                vin=vin
            )
            if response.get('statusResponse', {}) :
                self._state[vin].update(
                    {'heating': response.get('statusResponse', {})}
                )
                return True
            else:
                _LOGGER.debug(f'Could not fetch pre-heating: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
            if (err.status == 403 or err.status == 502):
                _LOGGER.debug(f'Could not fetch pre-heating, error 403/502 (not supported on car?), error: {err}')
            elif err.status == 401:
                _LOGGER.warning(f'Received "unauthorized" error while fetching data: {err}')
                self._session_logged_in = False
            elif err.satus != 200:
                _LOGGER.warning(f'Unhandled HTTP response: {err}')
            else:
                _LOGGER.warning(f'Could not fetch pre-heating (ClientResponseError), error: {err}')
            return False
        except Exception as err:
            _LOGGER.warning(f'Could not fetch pre-heating, error: {err}')
            return False
 #### Token handling ####
    @property
    async def validate_tokens(self):
        """Function to validate expiry of tokens."""
        idtoken = self._session_tokens['identity']['id_token']
        atoken = self._session_tokens['vwg']['access_token']
        id_exp = jwt.decode(idtoken, verify=False).get('exp', None)
        at_exp = jwt.decode(atoken, verify=False).get('exp', None)
        id_dt = datetime.fromtimestamp(int(id_exp))
        at_dt = datetime.fromtimestamp(int(at_exp))
        now = datetime.now()
        # We check if the tokens expire in the next minute
        later = now + timedelta(minutes=1)
        if now >= id_dt or now >= at_dt:
            _LOGGER.debug('Tokens have expired. Try to fetch new tokens.')
            if await self.refresh_tokens():
                _LOGGER.debug('Successfully refreshed tokens')
            else:
                return False
        elif later >= id_dt or later >= at_dt:
            _LOGGER.debug('Tokens about to expire. Try to fetch new tokens.')
            if await self.refresh_tokens():
                _LOGGER.debug('Successfully refreshed tokens')
            else:
                return False
        else:
            expString = id_dt.strftime('%Y-%m-%d %H:%M:%S')
            _LOGGER.debug(f'Tokens valid until {expString}')
        return True

    async def verify_tokens(self, token, type):
        """Function to verify JWT against JWK(s)."""
        if type == 'identity':
            req = await self._session.get(url = 'https://identity.vwgroup.io/oidc/v1/keys')
            keys = await req.json()
            audience = [
                CLIENT_ID, 
                "VWGMBB01DELIV1", 
                "https://api.vas.eu.dp15.vwg-connect.com", 
                "https://api.vas.eu.wcardp.io"
            ]
        elif type == 'vwg':
            req = await self._session.get(url = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/public/jwk/v1')
            keys = await req.json()
            audience = 'mal.prd.ece.vwg-connect.com'
        else:
            _LOGGER.debug('Not implemented')
            return False
        try:
            pubkeys = {}
            for jwk in keys['keys']:
                kid = jwk['kid']
                if jwk['kty'] == 'RSA':
                    pubkeys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(to_json(jwk))

            token_kid = jwt.get_unverified_header(token)['kid']
            if type == 'vwg':
                token_kid = 'VWGMBB01DELIV1.' + token_kid

            pubkey = pubkeys[token_kid]
            payload = jwt.decode(token, key=pubkey, algorithms=['RS256'], audience=audience)
            return True
        except Exception as error:
            _LOGGER.debug('Failed to verify token, error: %s' % error)
            return False

    async def refresh_tokens(self):
        """Function to refresh tokens."""
        try:
            tHeaders = {
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "sv-SE",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "okhttp/3.7.0",
                "X-App-Version": "3.2.6",
                "X-App-Name": "cz.skodaauto.connect",
                "X-Client-Id": "28cd30c6-dee7-4529-a0e6-b1e07ff90b79"
            }

            body = {
                'grant_type': 'refresh_token',
                'brand': 'Skoda',
                'refresh_token': self._session_tokens['identity']['refresh_token']
            }
            response = await self._session.post(
                url = "https://tokenrefreshservice.apps.emea.vwapps.io/refreshTokens",
                headers = tHeaders,
                data = body
            )
            if response.status == 200:
                tokens = await response.json()
                # Verify Token
                if not await self.verify_tokens(tokens['id_token'], 'identity'):
                    _LOGGER.warning('Token could not be verified!')
                for token in tokens:
                    self._session_tokens['identity'][token] = tokens[token]
            else:
                _LOGGER.warning('Something went wrong when refreshing Skoda tokens.')
                return False

            body = {
                'grant_type': 'id_token',
                'scope': 'sc2:fal',
                'token': self._session_tokens['identity']['id_token']
            }

            response = await self._session.post(
                url = "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token",
                headers = tHeaders,
                data = body,
                allow_redirects=True
            )
            if response.status == 200:
                tokens = await response.json()
                if not await self.verify_tokens(tokens['access_token'], 'vwg'):
                    _LOGGER.warning('Token could not be verified!')
                for token in tokens:
                    self._session_tokens['vwg'][token] = tokens[token]
            else:
                resp = await response.text()
                _LOGGER.warning('Something went wrong when refreshing API tokens. %s' % resp)
                return False
            return True
        except Exception as error:
            _LOGGER.warning(f'Could not refresh tokens: {error}')
            return False

    def vehicle(self, vin):
        """Return vehicle object for given vin."""
        return next(
            (
                vehicle
                for vehicle in self.vehicles
                if vehicle.unique_id.lower() == vin.lower()
            ), None
        )

    def vehicle_attrs(self, vehicle_url):
        return self._state.get(vehicle_url)

  # Attributes
    @property
    def vehicles(self):
        """Return list of Vehicle objects."""
        return self._vehicles

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
                    for instrument in vehicle.dashboard().instruments:
                        print(f' - {instrument.name} (domain:{instrument.component}) - {instrument.str_state}')
                    
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
