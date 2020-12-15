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
from utilities import find_path, is_valid_path, read_config, json_loads
from base64 import b64decode, b64encode

from aiohttp import ClientSession, ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST

#from .const import (
#    HEADERS_SESSION
#)

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
            _LOGGER.debug('Clear cookies and login.')
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

            _LOGGER.debug('Got OpenID configuration, logging in.')
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
            _LOGGER.debug('Succesfully sent email, trying password.')

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

            _LOGGER.debug('Succesfully sent password, extract authorization code and get tokens.')
            # Extract code and tokens
            self._session_tokens['jwt'] = {}
            jwtauth_code = parse_qs(urlparse(ref).fragment).get('code')[0]
            self._session_tokens['jwt']['access_token'] = parse_qs(urlparse(ref).fragment).get('access_token')[0]
            self._session_tokens['jwt']['id_token'] = parse_qs(urlparse(ref).fragment).get('id_token')[0]

            # Exchange Auth code for Skoda tokens
            tokenBody = {
                "auth_code": jwtauth_code,
                "id_token":  self._session_tokens['jwt']['id_token'], #jwtid_token,
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
            # Save tokens as "skoda", we will need this later for token refresh
            self._session_tokens['skoda'] = await req.json()

            # Get VW Group API tokens
            # https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token
            tokenBody2 =  {
                "grant_type": "id_token",
                "token": self._session_tokens['skoda']['id_token'],
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
            # Save tokens as "vwg", use theese for get/posts to VW Group API
            self._session_tokens['vwg'] = await req.json()

            # Update headers for requests, default to VWG token
            self._session_headers['Authorization'] = "Bearer " + self._session_tokens['vwg']['access_token'] #atoken
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
            #try:
            #    response.raise_for_status()
            #except aiohttp.client_exceptions.ClientResponseError as error:
            #    if response.status == 401:
            #        _LOGGER.debug(f'Error in aiohttp request: {error}')
            #        _LOGGER.debug(f'Headers: {self._session_tokens}')
            #        self._session_logged_in = False
            #        return False
            #    pass
            #else:
            #    pass
            if response.status not in (200, 204, 401, 429, 503):
                response.raise_for_status()
                #raise aiohttp.ClientResponseError()

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
        response = await self._request(METH_GET, self._make_url(url, vin))
        #if not response:
        #    _LOGGER.debug('Got invalid response, trying to login again.')
        #    await self._login()
        #else:
        #    return response
        return response

    async def post(self, url, vin='', **data):
        """Perform a post query to the online service."""
        if data:
            response = await self._request(METH_POST, self._make_url(url, vin), **data)
        else:
            response = await self._request(METH_POST, self._make_url(url, vin))
        #if not response:
        #    _LOGGER.debug('Got invalid response, trying to login again.')
        #    await self._login()
        #else:
        #    return response
        return response

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
                self.set_token('vwg')
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
            # Get VIN numbers and call update for each
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
            atoken = self._session_tokens['skoda']['access_token']
            sub = jwt.decode(atoken, verify=False).get('sub', None)
            await self.set_token('skoda')
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
                return True
            elif response.get('status_code', 0) == 204:
                _LOGGER.debug(f'Seems car is moving, HTTP 204 received from position')
                self._state[vin].update({ 'isMoving': True })
                self._state[vin].update({ 'rate_limit_remaining': 15 })
                return True
            else:
                _LOGGER.debug(f'Could not fetch position: {response}')
            return False
        except aiohttp.client_exceptions.ClientResponseError as err:
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
        idtoken = self._session_tokens['skoda']['id_token']
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
                'brand': 'skoda',
                'refresh_token': self._session_tokens['skoda']['refresh_token']
            }
            response = await self._session.post(
                url = "https://tokenrefreshservice.apps.emea.vwapps.io/refreshTokens",
                headers = tHeaders,
                data = body
            )
            if response.status == 200:
                tokens = await response.json()
                for token in tokens:
                    self._session_tokens['skoda'][token] = tokens[token]
            else:
                _LOGGER.warning('Something went wrong when refreshing Skoda tokens.')
                return False

            body = {
                'grant_type': 'id_token',
                'scope': 'sc2:fal',
                'token': self._session_tokens['skoda']['id_token']
            }
            #tHeaders['host'] = 'mbboauth-1d.prd.ece.vwg-connect.com'

            response = await self._session.post(
                url = "https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token",
                headers = tHeaders,
                data = body,
                allow_redirects=True
            )
            if response.status == 200:
                tokens = await response.json()
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

 #### Vehicle subclass handling- ####
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
        #return (Vehicle(self, url) for url in self._state)
        return self._vehicles

    @property
    def logged_in(self):
        return self._session_logged_in

class Vehicle:
    def __init__(self, conn, url):
        self._connection = conn
        self._url = url
        self._requests_remaining = -1
        self._request_in_progress = False
        self._request_result = 'None'
        self._climate_duration = 30

 #### API Functions ####
  # Base methods
    async def update(self):
        # await self._connection.update(request_data=False)
        await self._connection.update_vehicle(self)

    async def get(self, query):
        """Perform a query to the online service."""
        req = await self._connection.get(query, self._url)
        return req

    async def post(self, query, **data):
        """Perform a query to the online service."""
        req = await self._connection.post(query, self._url, **data)
        # Get the number of requests left to throttled:
        if req.get("rate_limit_remaining", False):
            _LOGGER.debug('Got X-RateLimit-Remaining. Reducing number of requests remaining from %s to %s' % (self._requests_remaining, req.get("rate_limit_remaining")))
            self.requests_remaining = req.get("rate_limit_remaining")
        return req

  # Request handling
    async def call(self, query, **data):
        """Make remote method call."""
        try:
            if not await self._connection.validate_tokens:
                _LOGGER.info('Session has expired. Initiating new login to Skoda Connect.')
                await self._connection._login()

            self._request_result = 'In queue'
            self._request_in_progress = True
            await self._connection.set_token('vwg')
            _LOGGER.debug('Session headers: %s' % self._connection._session_headers)
            res = await self.post(query, **data)
            # Aux heater actions
            if res.get('performActionResponse', {}).get('requestId', False):
                _LOGGER.info('Message delivered, requestId=%s', res.get('performActionResponse', {}).get('requestId', 0))
                return str(res.get('performActionResponse', {}).get('requestId', False))
            # Electric climatisation, charger and departuretimer
            elif res.get('action', {}).get('actionId', False):
                _LOGGER.info('Message delivered, actionId=%s', res.get('action', {}).get('actionId', 0))
                return str(res.get('action', {}).get('actionId', False))
            # Status refresh actions
            elif res.get('CurrentVehicleDataResponse', {}).get('requestId', False):
                _LOGGER.info('Message delivered, requestId=%s', res.get('CurrentVehicleDataResponse', {}).get('requestId', 0))
                return str(res.get('CurrentVehicleDataResponse', {}).get('requestId', False))
            # Car lock/unlock action
            elif res.get('rluActionResponse', {}).get('requestId', False):
                _LOGGER.info('Message delivered, requestId=%s', res.get('rluActionResponse', {}).get('requestId', 0))
                return str(res.get('rluActionResponse', {}).get('requestId', False))
            # Climatisation action
            elif res.get('climatisationActionResponse', {}).get('requestId', False):
                _LOGGER.info('Message delivered, requestId=%s', res.get('climatisationActionResponse', {}).get('requestId', 0))
                return str(res.get('climatisationActionResponse', {}).get('requestId', False))
            else:
                _LOGGER.warning(f'Failed to execute {query}, response is:{str(res)}')
                self._request_in_progress = False
                return

        except Exception as error:
            self._request_result = 'Failed to execute'
            self._request_in_progress = False
            _LOGGER.warning(f'Failure to execute: {error}')

    async def getRequestProgressStatus(self, requestId, sectionId, retryCount=36):
        #retry count means that after 36x5seconds=3 minutes it will give up and not wait for status
        retryCount -= 1
        if (retryCount == 0):
            _LOGGER.warning(f'Timeout of waiting for result of {requestId} in section {sectionId}. It doesnt mean it wasnt success...')
            self._request_result = 'Timeout'
            self._request_in_progress = False
            return

        try:
            if not await self._connection.validate_tokens:
                _LOGGER.info('Session has expired. Initiating new login to Skoda Connect.')
                await self._connection._login()

            if sectionId == 'climatisation':
                url = "fs-car/bs/$sectionId/v1/Skoda/CZ/vehicles/$vin/climater/actions/$requestId"
            elif sectionId == 'batterycharge':
                url = "fs-car/bs/$sectionId/v1/Skoda/CZ/vehicles/$vin/charger/actions/$requestId"
            elif sectionId == 'departuretimer':
                url = "fs-car/bs/$sectionId/v1/Skoda/CZ/vehicles/$vin/timer/actions/$requestId"
            elif sectionId == 'vsr':
                url = "fs-car/bs/$sectionId/v1/Skoda/CZ/vehicles/$vin/requests/$requestId/jobstatus"
            else:
                url = "fs-car/bs/$sectionId/v1/Skoda/CZ/vehicles/$vin/requests/$requestId/status"
            url = re.sub("\$sectionId", sectionId, url)
            url = re.sub("\$requestId", requestId, url)

            res = await self.get(url)
            # VSR refresh, aux heater and lock/unlock
            if res.get('requestStatusResponse', {}).get('status', False):
                 result = res.get('requestStatusResponse', {}).get('status', False)
                 if result == 'request_in_progress':
                    self._request_result = 'In progress'
                    _LOGGER.debug(f'Request {requestId}, sectionId {sectionId} still in progress, sleeping for 5 seconds and check status again...')
                    time.sleep(5)
                    return await self.getRequestProgressStatus(requestId, sectionId, retryCount)
                 elif result == 'request_fail':
                    self._request_result = 'Failed'
                    self._request_in_progress = False
                    error = res.get('requestStatusResponse', {}).get('error', None)
                    _LOGGER.warning(f'Request {requestId}, sectionId {sectionId} failed, error: {error}.')
                    return False
                 elif result == 'request_successful':
                    self._request_result = 'Success'
                    self._request_in_progress = False
                    _LOGGER.debug(f'Request was successful, result: {result}')
                    return True
                 else:
                    self._request_result = result
                    self._request_in_progress = False
                    _LOGGER.debug(f'Request result: {result}')
                    return True
            # For electric charging, climatisation and set departuretimers
            elif res.get('action', {}).get('actionState', False):
                result=res.get('action', {}).get('actionState', False)
                if result == 'queued' or result == 'fetched':
                    self._request_result = 'In progress'
                    _LOGGER.debug(f'Request {requestId}, sectionId {sectionId} still in progress, sleeping for 5 seconds and check status again...')
                    time.sleep(5)
                    return await self.getRequestProgressStatus(requestId, sectionId, retryCount)
                elif result == 'failed':
                    self._request_result = 'Failed'
                    self._request_in_progress = False
                    error = res.get('action', {}).get('errorCode', None)
                    _LOGGER.warning(f'Request {requestId}, sectionId {sectionId} failed, error: {error}.')
                elif result == 'succeeded':
                    self._request_result = 'Success'
                    self._request_in_progress = False
                    _LOGGER.debug(f'Request was successful, result: {result}')
                else:
                    self._request_result = result
                    self._request_in_progress = False
                    _LOGGER.debug(f'Request result: {result}')
                    return True
            else:
                self._request_result = 'Unknown'
                self._request_in_progress = False
                _LOGGER.warning(f'Incorrect response for status response for request={requestId}, section={sectionId}, response is:{str(res)}')
                return

        except Exception as error:
            self._request_result = 'Task exception'
            self._request_in_progress = False
            _LOGGER.warning(f'Failure during get request progress status: {error}')
            return

  # SPIN Token handling
    async def requestSecToken(self,spin,action="heating"):
        urls = {
            "lock":    "/api/rolesrights/authorization/v2/vehicles/$vin/services/rlu_v1/operations/LOCK/security-pin-auth-requested",
            "unlock":  "/api/rolesrights/authorization/v2/vehicles/$vin/services/rlu_v1/operations/UNLOCK/security-pin-auth-requested",
            "heating": "/api/rolesrights/authorization/v2/vehicles/$vin/services/rheating_v1/operations/P_QSACT/security-pin-auth-requested",
            "timer":   "/api/rolesrights/authorization/v2/vehicles/$vin/services/timerprogramming_v1/operations/P_SETTINGS_AU/security-pin-auth-requested",
            "rclima":  "/api/rolesrights/authorization/v2/vehicles/$vin/services/rclima_v1/operations/P_START_CLIMA_AU/security-pin-auth-requested"
        }
        try:
            response = await self.get(self._connection._make_url(urls.get(action), vin=self.vin))
            secToken = response["securityPinAuthInfo"]["securityToken"]
            challenge = response["securityPinAuthInfo"]["securityPinTransmission"]["challenge"]
            securpin = await self.generateSecurPin(challenge, spin)
            body = "{ \"securityPinAuthentication\": { \"securityPin\": { \"challenge\": \""+challenge+"\", \"securityPinHash\": \""+securpin+"\" }, \"securityToken\": \""+secToken+"\" }}"

            self._connection._session_headers["Content-Type"]="application/json"
            response = await self.post(self._connection._make_url('/api/rolesrights/authorization/v2/security-pin-auth-completed', vin=self.vin), data=body)
            del self._connection._session_headers["Content-Type"]
            return response["securityToken"]
        except Exception as err:
            _LOGGER.error(f'Could not generate security token (maybe wrong SPIN?), error: {err}')

    async def generateSecurPin(self, challenge, pin):
        pinArray = bytearray.fromhex(pin);
        byteChallenge = bytearray.fromhex(challenge);
        pinArray.extend(byteChallenge)
        return hashlib.sha512(pinArray).hexdigest()

 #### Vehicle Attributes ####
  # Vehicle info
    @property
    def attrs(self):
        return self._connection.vehicle_attrs(self._url)

    def has_attr(self, attr):
        return is_valid_path(self.attrs, attr)

    def get_attr(self, attr):
        return find_path(self.attrs, attr)

    def dashboard(self, **config):
        #Classic python notation
        from dashboardskoda import Dashboard
        return Dashboard(self, **config)
        #HA notation
        #from . import dashboardskoda
        #return dashboardskoda.Dashboard(self, **config)

    @property
    def vin(self):
        return self._url

    @property
    def unique_id(self):
        return self.vin

 #### Information from vehicle states ####
  # Car information
    @property
    def nickname(self):
        return self.attrs.get('carData', {}).get('nickname', None)

    @property
    def is_nickname_supported(self):
        if self.attrs.get('carData', {}).get('nickname', False):
            return True

    @property
    def deactivated(self):
        return self.attrs.get('carData', {}).get('deactivated', None)

    @property
    def is_deactivated_supported(self):
        if self.attrs.get('carData', {}).get('deactivated', False):
            return True

    @property
    def model(self):
        """Return model"""
        return self.attrs.get('carportData', {}).get('modelName', None)

    @property
    def is_model_supported(self):
        if self.attrs.get('carportData', {}).get('modelName', False):
            return True

    @property
    def model_year(self):
        """Return model year"""
        return self.attrs.get('carportData', {}).get('modelYear', None)

    @property
    def is_model_year_supported(self):
        if self.attrs.get('carportData', {}).get('modelYear', False):
            return True

    @property
    def model_image(self):
        #Not implemented for SKODA
        """Return model image"""
        return self.attrs.get('imageUrl')

    @property
    def is_model_image_supported(self):
        #Not implemented for SKODA
        if self.attrs.get('imageUrl', False):
            return True

  # Lights
    @property
    def parking_light(self):
        """Return true if parking light is on"""
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301010001'].get('value',0))
        if response != 2:
            return True
        else:
            return False

    @property
    def is_parking_light_supported(self):
        """Return true if parking light is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301010001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

  # Connection status
    @property
    def last_connected(self):
        """Return when vehicle was last connected to skoda connect."""
        last_connected_utc = self.attrs.get('StoredVehicleDataResponse').get('vehicleData').get('data')[0].get('field')[0].get('tsCarSentUtc')
        last_connected = last_connected_utc.replace(tzinfo=timezone.utc).astimezone(tz=None)
        return last_connected.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def is_last_connected_supported(self):
        """Return when vehicle was last connected to skoda connect."""
        if next(iter(next(iter(self.attrs.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})), None).get('field', {})), None).get('tsCarSentUtc', []):
            return True

  # Service information
    @property
    def distance(self):
        """Return vehicle odometer"""
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0101010002'].get('value',0)
        if value:
            return int(value)

    @property
    def is_distance_supported(self):
        """Return true if odometer is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0101010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def service_inspection(self):
        """Return time left for service inspection"""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010004'].get('value')

    @property
    def is_service_inspection_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0203010004' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def service_inspection_km(self):
        """Return time left for service inspection"""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010003'].get('value')

    @property
    def is_service_inspection_km_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0203010003' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def oil_inspection(self):
        """Return time left for service inspection"""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010002'].get('value')

    @property
    def is_oil_inspection_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0203010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False
    @property
    def oil_inspection_km(self):
        """Return time left for service inspection"""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010001'].get('value')

    @property
    def is_oil_inspection_km_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0203010001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def adblue_level(self):
        """Return adblue level."""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x02040C0001'].get('value',0)

    @property
    def is_adblue_level_supported(self):
        """Return true if adblue level is supported."""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x02040C0001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if "value" in self.attrs.get('StoredVehicleDataResponseParsed')['0x02040C0001']:
                    if self.attrs.get('StoredVehicleDataResponseParsed')['0x02040C0001'].get('value',0) is None:
                        return False
                    else:
                        return True
                else:
                    return False
            else:
                return False

  # Charger related states for EV and PHEV
    @property
    def charging(self):
        """Return battery level"""
        cstate = self.attrs.get('charger').get('status').get('chargingStatusData').get('chargingState').get('content', '')
        return 1 if cstate == 'charging' else 0

    @property
    def is_charging_supported(self):
        """Return true if charging is supported"""
        if self.attrs.get('charger', {}):
            if 'status' in self.attrs.get('charger'):
                if 'chargingStatusData' in self.attrs.get('charger')['status']:
                    if 'chargingState' in self.attrs.get('charger')['status']['chargingStatusData']:
                        return True
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False

    @property
    def battery_level(self):
        """Return battery level"""
        return self.attrs.get('charger').get('status').get('batteryStatusData').get('stateOfCharge').get('content', 0)

    @property
    def is_battery_level_supported(self):
        """Return true if battery level is supported"""
        if self.attrs.get('charger', {}):
            if 'status' in self.attrs.get('charger'):
                if 'batteryStatusData' in self.attrs.get('charger')['status']:
                    if 'stateOfCharge' in self.attrs.get('charger')['status']['batteryStatusData']:
                        return True
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False

    @property
    def charge_max_ampere(self):
        """Return charger current setting."""
        value = int(self.attrs.get('charger').get('settings').get('maxChargeCurrent').get('content'))
        if value == 254:
            return "Maximum"
        if value == 252:
            return "Reduced"
        if value == 0:
            return "Unknown"
        else:
            return value

    @property
    def is_charge_max_ampere_supported(self):
        """Return true if Charger Max Ampere is supported"""
        if self.attrs.get('charger', {}):
            if 'settings' in self.attrs.get('charger', {}):
                if 'maxChargeCurrent' in self.attrs.get('charger', {})['settings']:
                    return True
            else:
                return False

    @property
    def charging_cable_locked(self):
        """Return plug locked state"""
        response = self.attrs.get('charger')['status']['plugStatusData']['lockState'].get('content',0)
        if response == 'locked':
            return True
        else:
            return False

    @property
    def is_charging_cable_locked_supported(self):
        """Return true if plug locked state is supported"""
        if self.attrs.get('charger', {}):
            if 'status' in self.attrs.get('charger', {}):
                if 'plugStatusData' in self.attrs.get('charger').get('status', {}):
                    if 'lockState' in self.attrs.get('charger')['status'].get('plugStatusData', {}):
                        return True
        return False

    @property
    def charging_cable_connected(self):
        """Return plug locked state"""
        response = self.attrs.get('charger')['status']['plugStatusData']['plugState'].get('content',0)
        if response == 'connected':
            return False
        else:
            return True

    @property
    def is_charging_cable_connected_supported(self):
        """Return true if charging cable connected is supported"""
        if self.attrs.get('charger', {}):
            if 'status' in self.attrs.get('charger', {}):
                if 'plugStatusData' in self.attrs.get('charger').get('status', {}):
                    if 'plugState' in self.attrs.get('charger')['status'].get('plugStatusData', {}):
                        return True
        return False

    @property
    def charging_time_left(self):
        """Return minutes to charing complete"""
        if self.external_power:
            minutes = self.attrs.get('charger', {}).get('status', {}).get('batteryStatusData', {}).get('remainingChargingTime', {}).get('content', 0)
            if minutes:
                try:
                    if minutes == 65535: minutes = -1
                    return int(minutes)
                except Exception:
                    pass
        return 0

    @property
    def is_charging_time_left_supported(self):
        """Return true if charging is supported"""
        return self.is_charging_supported

    @property
    def external_power(self):
        """Return true if external power is connected."""
        check = self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('externalPowerSupplyState', {}).get('content', '')
        if check in ['stationConnected', 'available']:
            return True
        else:
            return False

    @property
    def is_external_power_supported(self):
        """External power supported."""
        if self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('externalPowerSupplyState', False):
            return True

    @property
    def energy_flow(self):
        """Return true if energy is flowing through charging port."""
        check = self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('energyFlow', {}).get('content', 'off')
        if check == 'on':
            return True
        else:
            return False

    @property
    def is_energy_flow_supported(self):
        """Energy flow supported."""
        if self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('energyFlow', False):
            return True

  # Vehicle location states
    @property
    def position(self):
        """Return  position."""
        posObj = self.attrs.get('findCarResponse')
        lat = int(posObj.get('Position').get('carCoordinate').get('latitude'))/1000000
        lng = int(posObj.get('Position').get('carCoordinate').get('longitude'))/1000000
        parkingTime = posObj.get('parkingTimeUTC')
        output = {
            "lat" : lat,
            "lng" : lng,
            "timestamp" : parkingTime
        }
        return output

    @property
    def is_position_supported(self):
        """Return true if vehichle has position."""
        if self.attrs.get('findCarResponse', {}).get('Position', {}).get('carCoordinate', {}).get('latitude', False):
            return True

    @property
    def vehicleMoving(self):
        """Return true if vehicle is moving."""
        return self.attrs.get('isMoving', False)

    @property
    def is_vehicleMoving_supported(self):
        """Return true if vehicle supports position."""
        if self.is_position_supported:
            return True

    @property
    def parkingTime(self):
        """Return timestamp of last parking time."""
        parkTime_utc = self.attrs.get('findCarResponse').get('parkingTimeUTC', 'Unknown')
        parkTime = parkTime_utc.replace(tzinfo=timezone.utc).astimezone(tz=None)
        return parkTime.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def is_parkingTime_supported(self):
        """Return true if vehicle parking timestamp is supported."""
        if 'parkingTimeUTC' in self.attrs.get('findCarResponse', {}):
            return True

  # Vehicle fuel level and range
    @property
    def electric_range(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008'].get('value',0)
        if value:
            return int(value)

    @property
    def is_electric_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301030008' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008']:
                    return True
                else:
                    return False
            else:
                return False

    @property
    def combustion_range(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030006'].get('value',0)
        if value:
            return int(value)

    @property
    def is_combustion_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301030006' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def combined_range(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030005'].get('value',0)
        if value:
            return int(value)

    @property
    def is_combined_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301030005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def fuel_level(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x030103000A'].get('value',0)
        if value:
            return int(value)

    @property
    def is_fuel_level_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030103000A' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

  # Climatisation settings
    @property
    def climatisation_target_temperature(self):
        """Return the target temperature from climater."""
        value = self.attrs.get('climater').get('settings').get('targetTemperature').get('content')
        if value:
            reply = float((value-2730)/10) 
            self._climatisation_target_temperature=reply
            return reply

    @property
    def is_climatisation_target_temperature_supported(self):
        """Return true if climatisation target temperature is supported."""
        if self.attrs.get('climater', {}):
            if 'settings' in self.attrs.get('climater', {}):
                if 'targetTemperature' in self.attrs.get('climater', {})['settings']:
                    return True
            else:
                return False

    @property
    def climatisation_without_external_power(self):
        """Return state of climatisation from battery power."""
        return self.attrs.get('climater').get('settings').get('climatisationWithoutHVpower').get('content', False)

    @property
    def is_climatisation_without_external_power_supported(self):
        """Return true if climatisation on battery power is supported."""
        if self.attrs.get('climater', {}):
            if 'settings' in self.attrs.get('climater', {}):
                if 'climatisationWithoutHVpower' in self.attrs.get('climater', {})['settings']:
                    return True
            else:
                return False

    @property
    def outside_temperature(self):
        """Return outside temp from VSR"""
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301020001'].get('value',0))
        if response:
            return float((response-2730)/10)
        else:
            return False

    @property
    def is_outside_temperature_supported(self):
        """Return true if outside temp is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301020001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if "value" in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301020001']:
                    return True
                else:
                    return False
            else:
                return False

  # Climatisation, electric
    @property
    def electric_climatisation(self):
        """Return status of climatisation."""
        climatisation_type = self.attrs.get('climater', {}).get('settings', {}).get('heaterSource', {}).get('content', '')
        status = self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', '')
        if status in ['heating', 'on'] and climatisation_type == 'electric':
            return True
        else:
            return False

    @property
    def is_electric_climatisation_supported(self):
        """Return true if vehichle has climater."""
        return self.is_climatisation_supported

    @property
    def auxiliary_climatisation(self):
        """Return status of auxiliary climatisation."""
        climatisation_type = self.attrs.get('climater', {}).get('settings', {}).get('heaterSource', {}).get('content', '')
        status = self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', '')
        if status in ['heatingAuxiliary', 'on'] and climatisation_type == 'auxiliary':
            return True
        else:
            return False

    @property
    def is_auxiliary_climatisation_supported(self):
        """Return true if vehicle has climater."""
        return self.is_climatisation_supported

    @property
    def is_climatisation_supported(self):
        """Return true if climatisation has State."""
        response = self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', '')
        if response != '':
            return True

    @property
    def window_heater(self):
        """Return status of window heater."""
        ret = False
        status_front = self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateFront', {}).get('content', '')
        if status_front == 'on':
            ret = True

        status_rear = self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateRear', {}).get('content', '')
        if status_rear == 'on':
            ret = True
        return ret

    @property
    def is_window_heater_supported(self):
        """Return true if vehichle has heater."""
        if self.is_electric_climatisation_supported:
            if self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateFront', {}).get('content', '') in ['on', 'off']:
                return True
            if self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateRear', {}).get('content', '') in ['on', 'off']:
                return True

  # Parking heater
    @property
    def pheater_duration(self):
        _LOGGER.debug(f'pheater getter, value is {self._climate_duration}')
        return self._climate_duration

    @pheater_duration.setter
    def pheater_duration(self, value):  
        _LOGGER.debug(f'pheater setter, value is {self.pheater_duration}')
        if value in [10, 20, 30, 40, 50, 60]:
            _LOGGER.debug(f'pheater setter, set value to: {value}')
            self._climate_duration = value
            _LOGGER.debug(f'pheater setter, value is now {self.pheater_duration}')
        else:
            _LOGGER.warning(f'Invalid value for duration: {value}')

    def is_pheater_duration_supported(self):
        return True #self.is_pheater_heating_supported

    @property
    def pheater_ventilation(self):
        """Return status of combustion climatisation."""
        return self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False) == 'ventilation'

    @property
    def is_pheater_ventilation_supported(self):
        """Return true if vehichle has combustion climatisation."""
        if self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False):
            return True

    @property
    def pheater_heating(self):
        """Return status of combustion engine heating."""
        return self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False) == 'heating'

    @property
    def is_pheater_heating_supported(self):
        """Return true if vehichle has combustion engine heating."""
        if self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False):
            return True

    @property
    def pheater_status(self):
        """Return status of combustion engine heating/ventilation."""
        return self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', 'Unknown')

    @property
    def is_pheater_status_supported(self):
        """Return true if vehichle has combustion engine heating/ventilation."""
        if self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False):
            return True

  # Windows
    @property
    def windows_closed(self):
        return (self.window_closed_left_front and self.window_closed_left_back and self.window_closed_right_front and self.window_closed_right_back)

    @property
    def is_windows_closed_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_left_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050001'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_left_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_right_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050005'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_right_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_left_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050003'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_left_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050003' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_right_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050007'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_right_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050007' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def sunroof_closed(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030105000B'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_sunroof_closed_supported(self):
        """Return true if sunroof state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030105000B' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if (int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030105000B'].get('value',0)) == 0):
                    return False
                else:
                    return True
            else:
                return False

  # Locks
    @property
    def door_locked(self):
        #LEFT FRONT
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040001'].get('value',0))
        if response != 2:
            return False
        #LEFT REAR
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040004'].get('value',0))
        if response != 2:
            return False
        #RIGHT FRONT
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040007'].get('value',0))
        if response != 2:
            return False
        #RIGHT REAR
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000A'].get('value',0))
        if response != 2:
            return False

        return True

    @property
    def is_door_locked_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def trunk_locked(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000D'].get('value',0))
        if response == 2:
            return True
        else:
            return False

    @property
    def is_trunk_locked_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030104000D' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

  # Doors, hood and trunk
    @property
    def hood_closed(self):
        """Return true if hood is closed"""
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040011'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_hood_closed_supported(self):
        """Return true if hood state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040011' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if (int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040011'].get('value',0)) == 0):
                    return False
                else:
                    return True
            else:
                return False

    @property
    def door_closed_left_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040002'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_left_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_right_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040008'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_right_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040008' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_left_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040005'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_left_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_right_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000B'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_right_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030104000B' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def trunk_closed(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000E'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_trunk_closed_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030104000E' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

  # Trip data
    @property
    def trip_last_entry(self):
        return self.attrs.get('tripstatistics', {})

    @property
    def trip_last_average_speed(self):
        return self.trip_last_entry.get('averageSpeed')

    @property
    def is_trip_last_average_speed_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageSpeed')) in (float, int):
            return True

    @property
    def trip_last_average_electric_consumption(self):
        value = self.trip_last_entry.get('averageElectricEngineConsumption')
        return float(value/10)

    @property
    def is_trip_last_average_electric_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageElectricEngineConsumption')) in (float, int):
            return True

    @property
    def trip_last_average_fuel_consumption(self):
        return int(self.trip_last_entry.get('averageFuelConsumption'))/10

    @property
    def is_trip_last_average_fuel_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageFuelConsumption')) in (float, int):
            return True

    @property
    def trip_last_average_auxillary_consumption(self):
        return self.trip_last_entry.get('averageAuxiliaryConsumption')

    @property
    def is_trip_last_average_auxillary_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageAuxiliaryConsumption')) in (float, int):
            return True

    @property
    def trip_last_duration(self):
        return self.trip_last_entry.get('traveltime')

    @property
    def is_trip_last_duration_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('traveltime')) in (float, int):
            return True

    @property
    def trip_last_length(self):
        return self.trip_last_entry.get('mileage')

    @property
    def is_trip_last_length_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('mileage')) in (float, int):
            return True

    @property
    def trip_last_recuperation(self):
        #Not implemented for SKODA
        return self.trip_last_entry.get('recuperation')

    @property
    def is_trip_last_recuperation_supported(self):
        #Not implemented for SKODA
        response = self.trip_last_entry
        if response and type(response.get('recuperation')) in (float, int):
            return True

    @property
    def trip_last_total_electric_consumption(self):
        #Not implemented for SKODA
        return self.trip_last_entry.get('totalElectricConsumption')

    @property
    def is_trip_last_total_electric_consumption_supported(self):
        #Not implemented for SKODA
        response = self.trip_last_entry
        if response and type(response.get('totalElectricConsumption')) in (float, int):
            return True

  # Departure Timers
    @property
    def timer1(self):
        timerSettings = self.attrs.get('timers',{}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])[0]
        timerProfile = self.attrs.get('timers',{}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])[0]
        return {**timerSettings, **timerProfile}        

    @property
    def timer2(self):
        timerSettings = self.attrs.get('timers',{}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])[1]
        timerProfile = self.attrs.get('timers',{}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])[1]
        return {**timerSettings, **timerProfile}        

    @property
    def timer3(self):
        timerSettings = self.attrs.get('timers',{}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])[2]
        timerProfile = self.attrs.get('timers',{}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])[2]
        return {**timerSettings, **timerProfile}        

  # Requests data
    @property
    def request_in_progress(self):
        return self._request_in_progress

    @property
    def is_request_in_progress_supported(self):
        """Request in progress is always supported."""
        return True

    @property
    def request_result(self):
        """Get last request result."""
        return self._request_result

    @property
    def is_request_result_supported(self):
        """Request result is supported if in progress is supported."""
        return self.is_request_in_progress_supported

    @property
    def requests_remaining(self):
        """Get remaining requests before throttled."""
        if self.attrs.get('rate_limit_remaining', False):
            _LOGGER.debug('rate_limit_remaining is set, update requests remaining to: %s' % self.attrs.get('rate_limit_remaining', ''))
            self.requests_remaining = self.attrs.get('rate_limit_remaining')
        return self._requests_remaining

    @requests_remaining.setter
    def requests_remaining(self, value):
        self._requests_remaining = value

    @property
    def is_requests_remaining_supported(self):
        return True if self._requests_remaining else False

 #### Vehicle Actions ####
  # Data refresh
    async def trigger_request_update(self):
        if self.is_request_in_progress_supported:
            if not self.request_in_progress:
                resp = await self.call('fs-car/bs/vsr/v1/skoda/CZ/vehicles/$vin/requests', data=None)
                if not resp:
                    _LOGGER.error('Failed to request vehicle update')
                else:
                    await self.getRequestProgressStatus(resp,"vsr")
                    await self.update()
                    return resp
            else:
                _LOGGER.warning('Another request is already in progress')
        else:
            _LOGGER.error('No request update support.')

  # Lock/Unlock actions
    async def door_lock(self, spin, action):
        """Remote lock and unlock actions."""
        if self.is_door_locked_supported:
            if not action in ['lock', 'unlock']:
                _LOGGER.warning('Invalid door lock action provided.')
                return False
            if spin:
                # Prepare data, headers and fetch security token
                data = '<rluAction xmlns="http://audi.de/connect/rlu"><action>' + action + '</action></rluAction>'
                secToken = await self.requestSecToken(spin, action)
                if 'Content-Type' in self._connection._session_headers:
                    contType = self._connection._session_headers['Content-Type']
                else:
                    contType = ''
                try:
                    self._connection._session_headers['X-mbbSecToken'] = secToken
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml"
                    resp = await self.call('fs-car/bs/rlu/v1/skoda/CZ/vehicles/$vin/actions', data=data)
                    if not resp:
                        _LOGGER.warning(f'Failed to {action} car.')
                    else:
                        _LOGGER.debug(f'Successfully {action}ed car!')
                        await self.getRequestProgressStatus(resp, 'rlu')
                        await self.update()
                except Exception as error:
                    _LOGGER.error(f'Failed to {action} car - {error}')
                #Cleanup headers
                if 'X-mbbSecToken' in self._connection._session_headers: del self._connection._session_headers['X-mbbSecToken']
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('Invalid SPIN provided.')
                return False
        else:
            _LOGGER.error('No car lock support.')
            return False

  # Parking heater petrol/diesel (non EV/PHEV or pre 2020 models?)
    async def pheater_climatisation(self, spin=False, mode='off'):
        """Set the mode for the parking heater."""
        if spin:
            if self.is_combustion_climatisation_supported:
                if not mode in ['heating', 'ventilation', 'off']:
                    _LOGGER.error(f'Invalid action for parking heater: {mode}')
                    return False
                secToken = await self.requestSecToken(spin, 'heating')
                self._connection._session_headers['x-mbbSecToken'] = secToken
                if mode == 'off':
                    data = {'performAction': {'quickstop': {'active': False }}}
                else:
                    data = {'performAction': {'quickstart': {'climatisationDuration': self.pheater_duration, 'startMode': mode, 'active': True }}}
                return await self.pheater_actions(data)
            else:
                _LOGGER.error('No parking heater support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def pheater_actions(self, data):
        """Petrol/diesel parking heater actions."""
        try:
            if 'Content-Type' in self._connection._session_headers:
                contType = self._connection._session_headers['Content-Type']
            else:
                contType = ''
            self._connection._session_headers['Content-Type'] = 'application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json'
            resp = await self.call('fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action', data=data)

            # Clean up headers             
            if 'x-mbbSecToken' in self._connection._session_headers: del self._connection._session_headers['x-mbbSecToken']
            if 'Content-Type' in self._connection._session_headers: del self._connection._session_headers['Content-Type']
            if contType: self._connection._session_headers['Content-Type']=contType

            if not resp:
                _LOGGER.warning('Failed to execute aux heater action.')
                return False
            else:
                await self.getRequestProgressStatus(resp, 'rs')
                await self.update()
                return True
        except Exception as error:
            _LOGGER.warning('Failed to execute aux heater action - %s' % error)
            if 'x-mbbSecToken' in self._connection._session_headers: del self._connection._session_headers['x-mbbSecToken']
            if 'Content-Type' in self._connection._session_headers: del self._connection._session_headers['Content-Type']
            if contType: self._connection._session_headers['Content-Type']=contType
            return False

  # Electric charging
    async def charger_actions(self, action):
        """Charging actions."""
        if not self.is_charging_supported:
           _LOGGER.error('No charging supported.')
           return False
        if action in ['start', 'stop']:
            try:
                data = {'action': {'type': action}}
                resp = await self.call('fs-car/bs/batterycharge/v1/Skoda/CZ/vehicles/$vin/charger/actions', json=data)
                if not resp:
                    _LOGGER.warning(f'Failed to {action} charging.')
                    return False
                else:
                    await self.getRequestProgressStatus(resp, 'batterycharge')
                    await self.update()
                    return resp
            except Exception as error:
                _LOGGER.warning(f'Failed to {action} charging - %s' % error)
                return False
        else:
            _LOGGER.error(f'Invalid charger action: {action}. Must be either start or stop')

  # Climatisation for EV/PHEVs
    async def climatisation_target(self, temperature=22):
        """Set climatisation target temp."""
        if self.is_electric_climatisation_supported or self.is_auxiliary_climatisation_supported:
            if not 16 <= temperature <= 30:
                _LOGGER.error(f'Set climatisation target temp to {temperature} is not supported.')
                return False
            temp = int((temperature+273)*10)
            data = {"action": {"settings": {"targetTemperature": temp},"type": "setSettings"}}
            return await self.climater_actions(data)
        else:
            _LOGGER.error('No climatisation support.')

    async def climatisation_wo_HVpower(self, mode=False):
        """Turn on/off electric climatisation from battery."""
        if self.is_electric_climatisation_supported:
            if not mode in [True, False]:
                _LOGGER.error(f'Set climatisation without external power to {mode} is not supported.')
                return False
            data = {"action": {"settings": {"climatisationWithoutHVpower": mode},"type": "setSettings"}}
            return await self.climater_actions(data)
        else:
            _LOGGER.error('No climatisation support.')

    async def window_heating(self, action='stop'):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            if not action in ['start', 'stop']:
                _LOGGER.error(f'Climatisation action: {action} not supported.')
                return False
            data = {"action": {"type": action+"WindowHeating"}}
            return await self.climater_actions(data)
        else:
            _LOGGER.error('No climatisation support.')

    async def climatisation(self, mode, spin=False):
        """Turn on/off climatisation with electric/auxiliary heater."""
        if self.is_electric_climatisation_supported:
            if mode in ['electric', 'auxiliary']:
                targetTemp = int((self.climatisation_target_temperature+273)*10)
                withoutHVPower = self.climatisation_without_external_power
                data = {'action':{'settings':{'climatisationWithoutHVpower': withoutHVPower, 'targetTemperature': targetTemp, 'heaterSource': mode},'type': 'startClimatisation'}}
            elif mode == 'off':
                data = {'action': {'type': 'stopClimatisation'}}
            else:
                _LOGGER.error(f'Invalid climatisation type: {mode}')
                return False
            # Get S-PIN security token if we are starting aux heater
            if mode == 'auxiliary' and spin:
                secToken = await self.requestSecToken(spin, 'rclima')
                self._connection._session_headers['X-securityToken'] = secToken
            elif mode == 'auxiliary':
                _LOGGER.error('S-PIN needs to be set to turn on auxiliary heater.')
                return False
            return await self.climater_actions(data)
        else:
            _LOGGER.error('No climatisation support.')

    async def climater_actions(self, data):
        """Execute climatisation actions."""
        try:
            resp = await self.call('fs-car/bs/climatisation/v1/Skoda/CZ/vehicles/$vin/climater/actions', json=data)
            if "X-securityToken" in self._connection._session_headers: del self._connection._session_headers["X-securityToken"]
            if not resp:
                _LOGGER.warning('Failed to execute climatisation action')
                return False
            else:
                await self.getRequestProgressStatus(resp,"climatisation")
                await self.update()
                return True
        except Exception as error:
            _LOGGER.warning('Failed to execute climatisation action - %s' % error)
            if "X-securityToken" in self._connection._session_headers: del self._connection._session_headers["X-securityToken"]
            return False

  # Departure timers
    async def set_schedule(self, data):
        """Set timer schedule and profiles."""
        """Expect data: [{'timerBasicSetting': {'targetTemperature': <temp>}}, {<key>: <value>}, ...]"""
        _LOGGER.debug('Got data: %s' % data)
        try:
            # Fetch current departuretimers from VAG servers
            needSPIN = False
            timerdata = {'action':{'timersAndProfiles':{}, 'type': 'setTimersAndProfiles'}}
            if self.attrs.get('timers', False):
                settings = self.attrs.get('timers').get('timersAndProfiles', {})
                timers = self.attrs.get('timers').get('timersAndProfiles').get('timerList').get('timer', {})
                profiles = self.attrs.get('timers').get('timersAndProfiles').get('timerProfileList').get('timerProfile', {})
                for d in timers:
                    d.pop('timestamp')
                    d['timerID'] = int(d['timerID'])
                    d['profileID'] = int(d['profileID'])
                    d['currentCalendarProvider'] = {}
                for d in profiles:
                    d.pop('timestamp')
                    d['profileID'] = int(d['profileID'])
                    d['targetChargeLevel'] = int(d['targetChargeLevel'])
                    d['chargeMaxCurrent'] = int(d['chargeMaxCurrent'])
                _LOGGER.debug("Settings: %s" % settings)
            else:
                _LOGGER.error("Timers and profiles didn't return data.")
                return False
            # Extract set temp from service call, if it exist.
            if data[0].get('timerBasicSetting', {}).get('targetTemperature', False):
                settings['timerBasicSetting'] = dict(data[0].get('timerBasicSetting', {}))
            else:
                settings['timerBasicSetting'] = {'targetTemperature': int((self.climatisation_target_temperature+273)*10)}

            # Loop through the service call data and update matching keys in departuretimer data
            for id in range(1, 4):
                for item in timers[id-1]:
                    for key in data[id]:
                        if key == item:
                            timers[id-1][key] = data[id][key]
                for item in profiles[id-1]:
                    for key in data[id]:
                        if key == item:
                            profiles[id-1][key] = data[id][key]
                        if key == "heaterSource" and data[id].get("heaterSource", False) == "automatic":
                            needSPIN = True
            # Prepare data to send
            timerdata['action']['timersAndProfiles'] = settings
            _LOGGER.debug("Settings now: %s" % settings)
            _LOGGER.debug("Update departure timers: %s" % timerdata)

            # Prepare headers
            if "Content-Type" in self._connection._session_headers:
                contType = self._connection._session_headers["Content-Type"]
            else:
                contType = ''
            self._connection._session_headers["Content-Type"] = "application/json; charset=UTF-8"

            try:
                url = "fs-car/bs/departuretimer/v1/skoda/CZ/vehicles/$vin/timer/actions"
                #data = dict(timerdata)
                # Get security token if needed (if aux heater is to be activated)
                if needSPIN:
                    secToken = await self.requestSecToken(spin, "departuretimer")
                    self._connection._session_headers["x-mbbSecToken"] = secToken
                _LOGGER.debug('Sending data with headers: %s' % self._connection._session_headers)
                # Send data and wait for response
                resp = await self.call(url, json=timerdata)
                if not resp:
                    _LOGGER.warning('Failed to set departure timers!')
                    return False
                else:
                    await self.getRequestProgressStatus(resp, "departuretimer")
                    await self.update()
            except Exception as error:
                _LOGGER.error('Failed to set departure timers, error: %s' % error)
                #Cleanup headers
                self._connection._session_headers["Content-Type"] = contType
                return False
            #Cleanup headers
            self._connection._session_headers["Content-Type"] = contType
            if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
            return True
        except Exception as error:
            _LOGGER.error("Couldn't set departure timers, error: %s" % error)
            return False

 #### Helper functions ####
    def __str__(self):
        return self.vin

    @property
    def json(self):
        def serialize(obj):
            if isintance(obj, datetime):
                return obj.isoformat()
        return to_json(
            OrderedDict(sorted(self.attrs.items())),
            indent=4,
            default=serialize
        )

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
