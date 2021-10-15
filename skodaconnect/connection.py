#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Communicate with Skoda Connect services."""
"""Fork of https://github.com/robinostlund/volkswagencarnet"""
"""Modified to utilize API calls derived from Android Apps instead of Web API"""
import re
import time
import logging
import asyncio
import hashlib
import jwt
import hmac
import string
import secrets

from sys import version_info, argv
from datetime import timedelta, datetime, timezone
from urllib.parse import urljoin, parse_qs, urlparse, urlencode
from json import dumps as to_json
from jwt.exceptions import ExpiredSignatureError
import aiohttp
from bs4 import BeautifulSoup
from base64 import b64decode, b64encode
from skodaconnect.__version__ import __version__ as lib_version
from skodaconnect.utilities import read_config, json_loads
from skodaconnect.vehicle import Vehicle
from skodaconnect.exceptions import (
    SkodaConfigException,
    SkodaAuthenticationException,
    SkodaAccountLockedException,
    SkodaTokenExpiredException,
    SkodaException,
    SkodaEULAException,
    SkodaThrottledException,
    SkodaLoginFailedException,
    SkodaInvalidRequestException,
    SkodaRequestInProgressException,
    SkodaServiceUnavailable
)

from aiohttp import ClientSession, ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST

from .const import (
    BRAND,
    COUNTRY,
    HEADERS_SESSION,
    HEADERS_AUTH,
    TOKEN_HEADERS,
    BASE_SESSION,
    BASE_AUTH,
    CLIENT_LIST,
    XCLIENT_ID,
    XAPPVERSION,
    XAPPNAME,
    USER_AGENT,
    APP_URI,
    MODELVIEWL,
    MODELVIEWS,
    MODELAPPID,
    MODELAPIKEY,
    MODELHOST,
    MODELAPI
)

version_info >= (3, 0) or exit('Python 3 required')

_LOGGER = logging.getLogger(__name__)

TIMEOUT = timedelta(seconds=30)

class Connection:
    """ Connection to Connect services """
  # Init connection class
    def __init__(self, session, username, password, fulldebug=False, **optional):
        """ Initialize """
        self._session = session
        self._lock = asyncio.Lock()
        self._session_fulldebug = fulldebug
        self._session_headers = HEADERS_SESSION.copy()
        self._session_base = BASE_SESSION
        self._session_auth_headers = HEADERS_AUTH.copy()
        self._session_cookies = ""
        self._session_nonce = self._getNonce()
        self._session_state = self._getState()

        self._session_auth_ref_url = BASE_SESSION
        self._session_spin_ref_url = BASE_SESSION
        self._session_first_update = False
        self._session_auth_username = username
        self._session_auth_password = password
        self._session_tokens = {}

        self._vehicles = []

        _LOGGER.info(f'Init Skoda Connect library, version {lib_version}')
        _LOGGER.debug(f'Using service {self._session_base}')


    def _clear_cookies(self):
        self._session._cookie_jar._cookies.clear()
        self._session_cookies = ''

    def _getNonce(self):
        chars = string.ascii_letters + string.digits
        text = ''.join(secrets.choice(chars) for i in range(10))
        sha256 = hashlib.sha256()
        sha256.update(text.encode())
        return (b64encode(sha256.digest()).decode('utf-8')[:-1])

    def _getState(self):
        return self._getNonce()

  # API login/logout/authorization
    async def doLogin(self):
        """Login method, clean login"""
        _LOGGER.info('Initiating new login')

        if len(self._session_tokens) > 0:
            _LOGGER.info('Revoking old tokens.')
            try:
                await self.logout()
            except:
                pass

        # Remove cookies and re-init session
        self._clear_cookies()
        self._vehicles.clear()
        self._session_tokens = {}
        self._session_headers = HEADERS_SESSION.copy()
        self._session_auth_headers = HEADERS_AUTH.copy()
        self._session_nonce = self._getNonce()
        self._session_state = self._getState()

        # Login with skoda client
        return await self._authorize('skoda')

    async def _authorize(self, client='connect'):
        """"Login" function. Authorize a certain client type and get tokens."""
        # Helper functions
        def extract_csrf(req):
            return re.compile('<meta name="_csrf" content="([^"]*)"/>').search(req).group(1)

        def extract_guest_language_id(req):
            return req.split('_')[1].lower()

        # Login/Authorization starts here
        try:
            self._session_headers = HEADERS_SESSION.copy()
            self._session_auth_headers = HEADERS_AUTH.copy()

            _LOGGER.debug(f'Starting authorization process for client {client}')
            req = await self._session.get(
                url='https://identity.vwgroup.io/.well-known/openid-configuration'
            )
            if req.status != 200:
                return False
            response_data =  await req.json()
            authorizationEndpoint = response_data['authorization_endpoint']
            authissuer = response_data['issuer']

            # Get authorization page (login page)
            if self._session_fulldebug:
                _LOGGER.debug(f'Get authorization page: "{authorizationEndpoint}"')
            try:
                req = await self._session.get(
                    url=authorizationEndpoint+\
                        '?redirect_uri='+APP_URI+\
                        '&nonce='+self._session_nonce+\
                        '&state='+self._session_state+\
                        '&response_type='+CLIENT_LIST[client].get('TOKEN_TYPES')+\
                        '&client_id='+CLIENT_LIST[client].get('CLIENT_ID')+\
                        '&scope='+CLIENT_LIST[client].get('SCOPE'),
                    headers=self._session_auth_headers,
                    allow_redirects=False
                )
                if req.headers.get('Location', False):
                    ref = req.headers.get('Location', '')
                    if 'error' in ref:
                        error = parse_qs(urlparse(ref).query).get('error', '')[0]
                        if 'error_description' in ref:
                            error = parse_qs(urlparse(ref).query).get('error_description', '')[0]
                            _LOGGER.info(f'Unable to login, {error}')
                        else:
                            _LOGGER.info(f'Unable to login.')
                        raise SkodaException(error)
                    else:
                        if self._session_fulldebug:
                            _LOGGER.debug(f'Got authorization endpoint: "{ref}"')
                        req = await self._session.get(
                            url=ref,
                            headers=self._session_auth_headers,
                            allow_redirects=False
                        )
                else:
                    _LOGGER.warning(f'Unable to fetch authorization endpoint')
                    raise SkodaException('Missing "location" header')
            except (SkodaException):
                raise
            except Exception as error:
                _LOGGER.warning(f'Failed to get authorization endpoint. {error}')
                raise SkodaException(error)

            # If we need to sign in (first token)
            if 'signin-service' in ref:
                _LOGGER.debug("Got redirect to signin-service")
                location = await self._signin_service(req, authissuer, authorizationEndpoint)
            else:
                # We are already logged on, shorter authorization flow
                location = req.headers.get('Location', None)

            # Follow all redirects until we reach the callback URL
            try:
                maxDepth = 10
                while not location.startswith(APP_URI):
                    if location is None:
                        raise SkodaException('Login failed')
                    if 'error' in location:
                        error = parse_qs(urlparse(location).query).get('error', '')[0]
                        if error == 'login.error.throttled':
                            timeout = parse_qs(urlparse(location).query).get('enableNextButtonAfterSeconds', '')[0]
                            raise SkodaAccountLockedException(f'Account is locked for another {timeout} seconds')
                        elif error == 'login.errors.password_invalid':
                            raise SkodaAuthenticationException('Invalid credentials')
                        else:
                            _LOGGER.warning(f'Login failed: {error}')
                        raise SkodaLoginFailedException(error)
                    if 'terms-and-conditions' in location:
                        raise SkodaEULAException('The terms and conditions must be accepted first at "https://www.skoda-connect.com/"')
                    if self._session_fulldebug:
                        _LOGGER.debug(f'Following redirect to "{location}"')
                    response = await self._session.get(
                        url=location,
                        headers=self._session_auth_headers,
                        allow_redirects=False
                    )
                    if response.headers.get('Location', False) is False:
                        _LOGGER.debug(f'Unexpected response: {await req.text()}')
                        raise SkodaAuthenticationException('User appears unauthorized')
                    location = response.headers.get('Location', None)
                    # Set a max limit on requests to prevent forever loop
                    maxDepth -= 1
                    if maxDepth == 0:
                        raise SkodaException('Too many redirects')
            except (SkodaException, SkodaEULAException, SkodaAuthenticationException, SkodaAccountLockedException, SkodaLoginFailedException):
                raise
            except Exception as e:
                # If we get an unhandled exception it should be because we can't redirect to the APP_URI URL and thus we have our auth code
                if 'code' in location:
                    if self._session_fulldebug:
                        _LOGGER.debug('Got code: %s' % location)
                    pass
                else:
                    _LOGGER.debug(f'Exception occured while logging in.')
                    raise SkodaLoginFailedException(e)

            _LOGGER.debug('Received authorization code, exchange for tokens.')
            # Extract code and tokens
            jwt_auth_code = parse_qs(urlparse(location).fragment).get('code')[0]
            jwt_id_token = parse_qs(urlparse(location).fragment).get('id_token')[0]
            tokenBody = {
                'auth_code': jwt_auth_code,
                'id_token':  jwt_id_token,
                'brand': BRAND
            }
            tokenURL = 'https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode'
            req = await self._session.post(
                url=tokenURL,
                headers=self._session_auth_headers,
                data = tokenBody,
                allow_redirects=False
            )
            if req.status != 200:
                if req.status >= 500:
                    raise SkodaServiceUnavailable(f'API returned HTTP status {req.status}')
                raise SkodaException(f'Token exchange failed. Request status: {req.status}')
            # Save access, identity and refresh tokens according to requested client
            token_data = await req.json()
            self._session_tokens[client] = {}
            for key in token_data:
                if '_token' in key:
                    self._session_tokens[client][key] = token_data[key]
            if 'error' in self._session_tokens[client]:
                error = self._session_tokens[client].get('error', '')
                if 'error_description' in self._session_tokens[client]:
                    error_description = self._session_tokens[client].get('error_description', '')
                    raise SkodaException(f'{error} - {error_description}')
                else:
                    raise SkodaException(error)
            if self._session_fulldebug:
                for key in self._session_tokens.get(client, {}):
                    if 'token' in key:
                        _LOGGER.debug(f'Got {key} for client {CLIENT_LIST[client].get("CLIENT_ID","")}, token: "{self._session_tokens.get(client, {}).get(key, None)}"')
            # Verify token, warn if problems are found
            verify = await self.verify_token(self._session_tokens[client].get('id_token', ''))
            if verify is False:
                _LOGGER.warning(f'Token for {client} is invalid!')
            elif verify is True:
                _LOGGER.debug(f'Token for {client} verified OK.')
            else:
                _LOGGER.warning(f'Token for {client} could not be verified, verification returned {verify}.')
        except (SkodaEULAException):
            _LOGGER.warning('Login failed, the terms and conditions might have been updated and need to be accepted. Login to https://www.skoda-connect.com and accept the new terms before trying again')
            raise
        except (SkodaAccountLockedException):
            _LOGGER.warning('Your account is locked, probably because of too many incorrect login attempts. Make sure that your account is not in use somewhere with incorrect password')
            raise
        except (SkodaAuthenticationException):
            _LOGGER.warning('Invalid credentials or invalid configuration. Make sure you have entered the correct credentials')
            raise
        except (SkodaException):
            _LOGGER.error('An API error was encountered during login, try again later')
            raise
        except (TypeError):
            _LOGGER.warning(f'Login failed for {self._session_auth_username}. The server might be temporarily unavailable, try again later. If the problem persists, verify your account at https://www.skoda-connect.com')
        except Exception as error:
            _LOGGER.error(f'Login failed for {self._session_auth_username}, {error}')
            return False
        return True

    async def _signin_service(self, html, authissuer, authorizationEndpoint):
        """Method to signin to Skoda Connect portal."""
        # Extract login form and extract attributes
        try:
            response_data = await html.text()
            responseSoup = BeautifulSoup(response_data, 'html.parser')
            mailform = dict()
            if responseSoup is None:
                raise SkodaLoginFailedException('Login failed, server did not return a login form')
            for t in responseSoup.find('form', id='emailPasswordForm').find_all('input', type='hidden'):
                if self._session_fulldebug:
                    _LOGGER.debug(f'Extracted form attribute: {t["name"], t["value"]}')
                mailform[t['name']] = t['value']
            #mailform = dict([(t['name'],t['value']) for t in responseSoup.find('form', id='emailPasswordForm').find_all('input', type='hidden')])
            mailform['email'] = self._session_auth_username
            pe_url = authissuer+responseSoup.find('form', id='emailPasswordForm').get('action')
        except Exception as e:
            _LOGGER.error('Failed to extract user login form.')
            raise

        # POST email
        # https://identity.vwgroup.io/signin-service/v1/{CLIENT_ID}/login/identifier
        self._session_auth_headers['Referer'] = authorizationEndpoint
        self._session_auth_headers['Origin'] = authissuer
        _LOGGER.debug(f"Start authorization for user {self._session_auth_username}")
        req = await self._session.post(
            url = pe_url,
            headers = self._session_auth_headers,
            data = mailform
        )
        if req.status != 200:
            raise SkodaException('Authorization request failed')
        try:
            response_data = await req.text()
            responseSoup = BeautifulSoup(response_data, 'html.parser')
            pwform = {}
            for t in responseSoup.find('form', id='credentialsForm').find_all('input', type='hidden'):
                if self._session_fulldebug:
                    _LOGGER.debug(f'Extracted form attribute: {t["name"], t["value"]}')
                pwform[t['name']] = t['value']
            #pwform = dict([(t['name'],t['value']) for t in responseSoup.find('form', id='credentialsForm').find_all('input', type='hidden')])
            pwform['password'] = self._session_auth_password
            pw_url = authissuer+responseSoup.find('form', id='credentialsForm').get('action')
        except Exception as e:
            if responseSoup.find('form', id='credentialsForm') is None:
                raise SkodaAuthenticationException("Invalid username")
            raise SkodaAuthenticationException("Invalid username or service unavailable")

        # POST password
        # https://identity.vwgroup.io/signin-service/v1/{CLIENT_ID}/login/authenticate
        self._session_auth_headers['Referer'] = pe_url
        self._session_auth_headers['Origin'] = authissuer
        _LOGGER.debug(f"Finalizing login")
        if self._session_fulldebug:
            _LOGGER.debug(f'Using login action url: "{pw_url}"')
        req = await self._session.post(
            url=pw_url,
            headers=self._session_auth_headers,
            data = pwform,
            allow_redirects=False
        )
        return req.headers.get('Location', None)

    async def _getAPITokens(self):
        """Method to acquire VW-Group API tokens."""
        try:
            # Check for valid 'connect' token
            token = self._session_tokens.get('connect', {}).get('id_token', None)
            if token is None:
                _LOGGER.debug('Client "connect" token is missing, call to authorize the client.')
                if await self._authorize('connect') is True:
                    token = self._session_tokens.get('connect', {}).get('id_token', None)
                else:
                    raise SkodaAuthenticationException('Failed to authorize client "connect"')

            # If connect token is not valid, try to refresh it
            if not await self.validate_token(token):
                # Try to refresh "Connect" token
                if not await self.refresh_token('connect'):
                    raise SkodaTokenExpiredException('Token is invalid for client "connect"')

            # https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token
            tokenBody2 =  {
                'token': self._session_tokens['connect']['id_token'],
                'grant_type': 'id_token',
                'scope': 'sc2:fal'
            }
            _LOGGER.debug('Trying to fetch api tokens.')
            req = await self._session.post(
                url='https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token',
                headers= {
                    'User-Agent': USER_AGENT,
                    'X-App-Version': XAPPVERSION,
                    'X-App-Name': XAPPNAME,
                    'X-Client-Id': XCLIENT_ID,
                },
                data = tokenBody2,
                allow_redirects=False
            )
            if req.status > 400:
                _LOGGER.debug('API token request failed.')
                raise SkodaException(f'API token request returned with status code {req.status}')
            else:
                # Save tokens as "vwg", use theese for get/posts to VW Group API
                token_data = await req.json()
                self._session_tokens['vwg'] = {}
                for key in token_data:
                    if '_token' in key:
                        self._session_tokens['vwg'][key] = token_data[key]
                if 'error' in self._session_tokens['vwg']:
                    error = self._session_tokens['vwg'].get('error', '')
                    if 'error_description' in self._session_tokens['vwg']:
                        error_description = self._session_tokens['vwg'].get('error_description', '')
                        raise SkodaException(f'{error} - {error_description}')
                    else:
                        raise SkodaException(error)
                if not await self.verify_token(self._session_tokens['vwg'].get('access_token', '')):
                    _LOGGER.warning('VW-Group API token could not be verified!')
                else:
                    _LOGGER.debug('VW-Group API token verified OK.')

            # Update headers for requests, defaults to using VWG token
            self._session_headers['Authorization'] = 'Bearer ' + self._session_tokens['vwg']['access_token']
        #except Exception as error:
        #    _LOGGER.error(f'Failed to fetch VW-Group API tokens, {error}')
        #    return False
        except:
            raise
        return True

    async def terminate(self):
        """Log out from connect services"""
        _LOGGER.info(f'Initiating logout')
        await self.logout()

    async def logout(self):
        """Logout, revoke tokens."""
        self._session_headers.pop('Authorization', None)
        self._session_headers.pop('tokentype', None)
        self._session_headers['Content-Type'] = 'application/x-www-form-urlencoded'

        for client in self._session_tokens:
            # Ignore identity tokens
            for token_type in (
                token_type
                for token_type in self._session_tokens[client]
                if token_type in ['refresh_token', 'access_token']
            ):
                # VW-Group tokens need their own data and url
                if client == 'vwg':
                    params = {
                        'token': self._session_tokens[client][token_type],
                        'token_type_hint': token_type
                    }
                    revoke_url = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/revoke'
                else:
                    params = {
                        "token": self._session_tokens[client][token_type],
                        "brand": BRAND
                    }
                    revoke_url = 'https://tokenrefreshservice.apps.emea.vwapps.io/revokeToken'

                # Only VW-Group access_token is revokeable
                if not client == 'vwg' and token_type == 'access_token':
                    pass
                # Revoke tokens
                else:
                    try:
                        if await self.post(revoke_url, data = params):
                            _LOGGER.info(f'Revocation of "{token_type}" for client "{client}" successful')
                            # Remove token info
                            self._session_tokens[client][token_type] = None
                        else:
                            _LOGGER.warning(f'Revocation of "{token_type}" for client "{client}" failed')
                    except Exception as e:
                        _LOGGER.info(f'Revocation failed with error: {e}')
                        pass

  # HTTP methods to API
    async def get(self, url, vin=''):
        """Perform a HTTP GET."""
        try:
            response = await self._request(METH_GET, url)
            return response
        except aiohttp.client_exceptions.ClientResponseError as error:
            data = {
                'status_code': error.status,
                'error': error.code,
                'error_description': error.message,
                'response_headers': error.headers,
                'request_info': error.request_info
            }
            if error.status == 401:
                _LOGGER.warning('Received "Unauthorized" while fetching data.\nThis can occur if tokens expired or refresh service is unavailable.')
            elif error.status == 400:
                _LOGGER.error('Received "Bad Request" from server.\nThe request might be malformed or not implemented correctly for this vehicle.')
            elif error.status == 412:
                _LOGGER.debug('Received "Pre-condition failed".\nService might be temporarily unavailable.')
            elif error.status == 500:
                _LOGGER.info('Received "Internal server error".\nThe service is temporarily unavailable.')
            elif error.status == 502:
                _LOGGER.info('Received "Bad gateway".\nEither the endpoint is temporarily unavailable or not supported for this vehicle.')
            elif 400 <= error.status <= 499:
                _LOGGER.error('Received unhandled error indicating client-side problem.\nRestart or try again later.')
            elif 500 <= error.status <= 599:
                _LOGGER.error('Received unhandled error indicating server-side problem.\nThe service might be temporarily unavailable.')
            else:
                _LOGGER.error('Received unhandled error while requesting API endpoint.')
            _LOGGER.debug(f'HTTP request information: {data}')
            return data
        except Exception as e:
            _LOGGER.debug(f'Got non HTTP related error: {e}')

    async def post(self, url, **data):
        """Perform a HTTP POST."""
        if data:
            return await self._request(METH_POST, url, **data)
        else:
            return await self._request(METH_POST, url)

    async def _request(self, method, url, **kwargs):
        """Perform a HTTP query"""
        if self._session_fulldebug:
            _LOGGER.debug(f'HTTP {method} "{url}"')
        async with self._session.request(
            method,
            url,
            headers=self._session_headers,
            timeout=ClientTimeout(total=TIMEOUT.seconds),
            cookies=self._session_cookies,
            raise_for_status=False,
            **kwargs
        ) as response:
            response.raise_for_status()

            # Update cookie jar
            if self._session_cookies != '':
                self._session_cookies.update(response.cookies)
            else:
                self._session_cookies = response.cookies

            try:
                if response.status == 204:
                    res = {'status_code': response.status}
                elif response.status >= 200 or response.status <= 300:
                    # If this is a revoke token url, expect Content-Length 0 and return
                    if int(response.headers.get('Content-Length', 0)) == 0 and 'revoke' in url:
                        if response.status == 200:
                            return True
                        else:
                            return False
                    else:
                        res = await response.json(loads=json_loads)
                else:
                    res = {}
                    _LOGGER.debug(f'Not success status code [{response.status}] response: {response}')
                if 'X-RateLimit-Remaining' in response.headers:
                    res['rate_limit_remaining'] = response.headers.get('X-RateLimit-Remaining', '')
            except Exception as e:
                res = {}
                _LOGGER.debug(f'Something went wrong [{response.status}] response: {response}, error: {e}')
                return res

            if self._session_fulldebug:
                _LOGGER.debug(f'Request for "{url}" returned with status code [{response.status}], response: {res}')
            else:
                _LOGGER.debug(f'Request for "{url}" returned with status code [{response.status}]')
            return res

    async def _data_call(self, query, **data):
        """Function for POST actions with error handling."""
        try:
            response = await self.post(query, **data)
            _LOGGER.debug(f'Data call returned: {response}')
            return response
        except aiohttp.client_exceptions.ClientResponseError as error:
            _LOGGER.debug(f'Request failed. Data: {data}, HTTP request headers: {self._session_headers}')
            if error.status == 401:
                _LOGGER.error('Unauthorized')
            elif error.status == 400:
                _LOGGER.error(f'Bad request')
            elif error.status == 429:
                _LOGGER.warning('Too many requests. Further requests can only be made after the end of next trip in order to protect your vehicles battery.')
                return 429
            elif error.status == 500:
                _LOGGER.error('Internal server error, server might be temporarily unavailable')
            elif error.status == 502:
                _LOGGER.error('Bad gateway, this function may not be implemented for this vehicle')
            else:
                _LOGGER.error(f'Unhandled HTTP exception: {error}')
            #return False
        except Exception as error:
            _LOGGER.error(f'Failure to execute: {error}')
        return False

  # Class get data functions
    async def update_all(self):
        """Update status."""
        try:
            await self.set_token('vwg')
            # Get all Vehicle objects and update in parallell
            update_list = []
            for vehicle in self.vehicles:
                if vehicle.vin not in update_list:
                    _LOGGER.debug(f'Adding {vehicle.vin} for data refresh')
                    update_list.append(vehicle.update())
                else:
                    _LOGGER.debug(f'VIN {vehicle.vin} is already queued for data refresh')

            # Wait for all data updates to complete
            if len(update_list) == 0:
                _LOGGER.info('No vehicles in account to update')
            else:
                _LOGGER.debug('Calling update function for all vehicles')
                await asyncio.gather(*update_list)
            return True
        except (IOError, OSError, LookupError, Exception) as error:
            _LOGGER.warning(f'An error was encountered during interaction with the API: {error}')
        except:
            raise
        return False

    async def get_vehicles(self):
        """Fetch vehicle information from user profile."""
        skoda_vehicles = []

        # Check if user needs to update consent
        try:
            await self.set_token('connect')
            consent = await self.getConsentInfo()
            if isinstance(consent, dict):
                _LOGGER.debug(f'Consent returned {consent}')
                if 'status' in consent.get('mandatoryConsentInfo', []):
                    if consent.get('mandatoryConsentInfo', [])['status'] != 'VALID':
                        _LOGGER.error(f'The user needs to update consent for {consent.get("mandatoryConsentInfo", [])["id"]}. If problems are encountered please visit the web portal first and accept terms and conditions.')
                        #raise SkodaEULAException(f'User needs to update consent for {consent.get("mandatoryConsentInfo", [])["id"]}')
                elif len(consent.get('missingMandatoryFields', [])) > 0:
                    _LOGGER.error(f'Missing mandatory field for user: {consent.get("missingMandatoryFields", [])[0].get("name", "")}. If problems are encountered please visit the web portal first and accept terms and conditions.')
                    #raise SkodaEULAException(f'Missing mandatory field for user: {consent.get("missingMandatoryFields", [])[0].get("name", "")}')
                else:
                    _LOGGER.debug('User consent is valid, no missing information for profile')
            else:
                _LOGGER.debug('Could not fetch consent information. If problems are encountered please visit the web portal first and make sure that no new terms and conditions need to be accepted.')
        except:
            _LOGGER.debug('Could not fetch consent information. If problems are encountered please visit the web portal first and make sure that no new terms and conditions need to be accepted.')
            #raise

        # Authorize for "skoda" client and get vehicles from garage endpoint
        try:
            await self.set_token('skoda')
            response = await self.get(
                'https://api.connect.skoda-auto.cz/api/v2/garage/vehicles'
            )
            # Check that response is a list
            if isinstance(response, list):
                skoda_vehicles = response
        except:
            raise

        # If Skoda API return no cars, fallback to VW-Group API
        if len(skoda_vehicles) == 0:
            _LOGGER.debug('Skoda native API returned no vehicles. Using fallback VW-Group API.')
            try:
                await self.set_token('vwg')
                self._session_headers.pop('Content-Type', None)
                response = await self.get(
                    url=f'https://msg.volkswagen.de/fs-car/usermanagement/users/v1/{BRAND}/{COUNTRY}/vehicles'
                )

                if response.get('userVehicles', {}).get('vehicle', False):
                    _LOGGER.debug('Found vehicle(s) associated with account.')
                    for vehicle in response.get('userVehicles').get('vehicle'):
                        await self.set_token('skoda')
                        vehicle_info = await self.get(url=f'https://api.connect.skoda-auto.cz/api/v2/vehicles/{vehicle}')
                        if vehicle_info.get('vehicleSpecification', False):
                            vehicle_info['vin'] = vehicle
                            skoda_vehicles.append(vehicle_info)
                        else:
                            _LOGGER.warning(f"Failed to aquire information about vehicle with VIN {vehicle}")
            except:
                raise

        # If neither API returns any vehicles, raise an error
        if len(skoda_vehicles) == 0:
            raise SkodaConfigException("No vehicles were found for given account!")

        # Get vehicle connectivity information
        else:
            try:
                for vehicle in skoda_vehicles:
                    _LOGGER.debug(f'Checking vehicle {vehicle}')
                    vin = vehicle.get('vin', '')
                    specs = vehicle.get('specification', vehicle.get('vehicleSpecification', ''))
                    connectivity = []
                    for service in vehicle.get('connectivities', []):
                        if isinstance(service, str):
                            connectivity.append(service)
                        elif isinstance(service, dict):
                            connectivity.append(service.get('type', ''))

                    capabilities = []
                    for capability in vehicle.get('capabilities', []):
                        capabilities.append(capability.get('id', ''))
                    vehicle = {
                        'vin': vin,
                        'connectivities': connectivity,
                        'capabilities': capabilities,
                        'specification': specs,
                    }
                    # Check if object already exist
                    _LOGGER.debug(f'Check if vehicle exists')
                    if self.vehicle(vin) is not None:
                        _LOGGER.debug(f'Vehicle with VIN number {vin} already exist.')
                        car = Vehicle(self, vehicle)
                        if not car == self.vehicle(vehicle):
                            _LOGGER.debug(f'Updating {vehicle} object')
                            self._vehicles.pop(vehicle)
                            self._vehicles.append(Vehicle(self, vehicle))
                    else:
                        _LOGGER.debug(f'Adding vehicle {vin}, with connectivities: {connectivity}')
                        self._vehicles.append(Vehicle(self, vehicle))
            except:
                raise SkodaLoginFailedException("Unable to fetch associated vehicles for account")
        # Update data for all vehicles
        await self.update_all()

        return skoda_vehicles

 #### API get data functions ####
   # Profile related functions
    async def getConsentInfo(self):
        """Get consent information for user."""
        try:
            await self.set_token('connect')
            atoken = self._session_tokens['connect']['access_token']
            # Try old pyJWT syntax first
            try:
                subject = jwt.decode(atoken, verify=False).get('sub', None)
            except:
                subject = None
            # Try new pyJWT syntax if old fails
            if subject is None:
                try:
                    exp = jwt.decode(atoken, options={'verify_signature': False}).get('sub', None)
                except:
                    raise Exception("Could not extract sub attribute from token")

            data = {'scopeId': 'commonMandatoryFields'}
            response = await self.post(f'https://profileintegrityservice.apps.emea.vwapps.io/iaa/pic/v1/users/{subject}/check-profile', json=data)
            if response.get('mandatoryConsentInfo', False):
                data = {
                    'consentInfo': response
                }
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch realCarData, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch consent information')
        except Exception as error:
            _LOGGER.debug(f'Could not get consent information, error {error}')
        return False

    async def getRealCarData(self):
        """Get car information from customer profile, VIN, nickname, etc."""
        try:
            await self.set_token('connect')
            _LOGGER.debug("Attempting extraction of jwt subject from identity token.")
            atoken = self._session_tokens['connect']['access_token']
            # Try old pyJWT syntax first
            try:
                subject = jwt.decode(atoken, verify=False).get('sub', None)
            except:
                subject = None
            # Try new pyJWT syntax if old fails
            if subject is None:
                try:
                    subject = jwt.decode(atoken, options={'verify_signature': False}).get('sub', None)
                except:
                    raise Exception("Could not extract sub attribute from token")

            response = await self.get(
                f'https://customer-profile.apps.emea.vwapps.io/v2/customers/{subject}/realCarData'
            )
            if response.get('realCars', False):
                data = {
                    'realCars': response.get('realCars', {})
                }
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch realCarData, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch realcar data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch realCarData, error: {error}')
        return False

   # Vehicle related functions
    async def getHomeRegion(self, vin):
        """Get API requests base url for VIN."""
        try:
            await self.set_token('vwg')
            response = await self.get(f'https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion', vin)
            self._session_auth_ref_url = response['homeRegion']['baseUri']['content'].split('/api')[0].replace('mal-', 'fal-') if response['homeRegion']['baseUri']['content'] != 'https://mal-1a.prd.ece.vwg-connect.com/api' else 'https://msg.volkswagen.de'
            self._session_spin_ref_url = response['homeRegion']['baseUri']['content'].split('/api')[0]
            return response['homeRegion']['baseUri']['content']
        except Exception as error:
            _LOGGER.debug(f'Could not get homeregion, error {error}')
        return False

    async def getOperationList(self, vin):
        """Collect operationlist for VIN, supported/licensed functions."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_spin_ref_url,
                    f'/api/rolesrights/operationlist/v3/vehicles/{vin}'
                )
            )
            if response.get('operationList', False):
                data = response.get('operationList', {})
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch operation list, HTTP status code: {response.get("status_code")}')
                data = response
            else:
                _LOGGER.info(f'Could not fetch operation list: {response}')
                data = {'error': 'unknown'}
        except Exception as error:
            _LOGGER.warning(f'Could not fetch operation list, error: {error}')
            data = {'error': 'unknown'}
        return data

    async def getModelImageURL(self, vin, size):
        """Construct the URL for the model image."""
        try:
            # Construct message to be encrypted
            date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%mZ')
            if size in ['S', 's', 'Small', 'small']:
                message = MODELAPPID +'\n'+ MODELAPI +'?vin='+ vin +'&view='+ MODELVIEWS +'&date='+ date
            else:
                message = MODELAPPID +'\n'+ MODELAPI +'?vin='+ vin +'&view='+ MODELVIEWL +'&date='+ date
            # Construct hmac SHA-256 key object and encode the message
            digest = hmac.new(MODELAPIKEY, msg=message.encode(), digestmod=hashlib.sha256).digest()
            b64enc = {'sign': b64encode(digest).decode()}
            sign = urlencode(b64enc)
            # Construct the URL
            if size in ['S', 's', 'Small', 'small']:
                path = MODELAPI +'?vin='+ vin +'&view='+ MODELVIEWS +'&appId='+ MODELAPPID +'&date='+ date +'&'+ sign
            else:
                path = MODELAPI +'?vin='+ vin +'&view='+ MODELVIEWL +'&appId='+ MODELAPPID +'&date='+ date +'&'+ sign
            url = MODELHOST + path
            try:
                response = await self._session.get(
                    url=url,
                    allow_redirects=False
                )
                if response.headers.get('Location', False):
                    return response.headers.get('Location').split('?')[0]
                else:
                    _LOGGER.debug('Could not fetch Model image URL, request returned with status code {response.status_code}')
            except:
                _LOGGER.debug('Could not fetch Model image URL')
        except:
            _LOGGER.debug('Could not fetch Model image URL, message signing failed.')
        return None

    async def getVehicleStatusReport(self, vin):
        """Get stored vehicle status report (Connect services)."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/vsr/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/status'
                )
            )
            if response.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})[0].get('field', {})[0] :
                data = {
                    'StoredVehicleDataResponse': response.get('StoredVehicleDataResponse', {}),
                    'StoredVehicleDataResponseParsed': dict([(e['id'],e if 'value' in e else '') for f in [s['field'] for s in response['StoredVehicleDataResponse']['vehicleData']['data']] for e in f])
                }
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch vehicle status report, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch status data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch StoredVehicleDataResponse, error: {error}')
        return False

    async def getVehicleStatus(self, vin):
        """Get stored vehicle status (SmartLink)."""
        try:
            await self.set_token('smartlink')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'https://api.connect.skoda-auto.cz/api/v1/vehicle-status/{vin}'
                )
            )
            if response:
                data = {
                    'vehicle_status': response
                }
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch vehicle status, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch vehicle status via SmartLink')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch SmartLink vehicle status, error: {error}')
        return False

    async def getTripStatistics(self, vin):
        """Get short term trip statistics."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/tripstatistics/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/tripdata/shortTerm?newest'
                )
            )
            if response.get('tripData', {}):
                data = {'tripstatistics': response.get('tripData', {})}
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch trip statistics, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info(f'Unhandled error while trying to fetch trip statistics')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch trip statistics, error: {error}')
        return False

    async def getPosition(self, vin):
        """Get position data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/cf/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/position'
                )
            )
            if response.get('findCarResponse', {}):
                data = {
                    'findCarResponse': response.get('findCarResponse', {}),
                    'isMoving': False
                }
                return data
            elif response.get('status_code', {}):
                if response.get('status_code', 0) == 204:
                    _LOGGER.debug(f'Seems car is moving, HTTP 204 received from position')
                    data = {
                        'isMoving': True,
                        'rate_limit_remaining': 15
                    }
                    return data
                else:
                    _LOGGER.warning(f'Could not fetch position, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch positional data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch position, error: {error}')
        return False

    async def getDeparturetimer(self, vin):
        """Get departure timers."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/departuretimer/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer'
                )
            )
            if response.get('timer', {}):
                data = {'departuretimer': response.get('timer', {})}
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch timers, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unknown error while trying to fetch data for departure timers')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch timers, error: {error}')
        return False

    async def getTimers(self, vin):
        """Get timers data (New Skoda API)."""
        try:
            await self.set_token('connect')
            response = await self.get(f'https://api.connect.skoda-auto.cz/api/v1/air-conditioning/{vin}/timers')
            if response.get('timers', []):
                data = {'timers': response.get('timers', [])}
                return data
            elif response.get('status_code', False):
                _LOGGER.warning(f'Could not fetch timers, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch timers data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch timers, error: {error}')
        return False

    async def getClimater(self, vin):
        """Get climatisation data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/climatisation/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater'
                )
            )
            if response.get('climater', {}):
                data = {'climater': response.get('climater', {})}
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch climatisation, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch climatisation data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch climatisation, error: {error}')
        return False

    async def getAirConditioning(self, vin):
        """Get air-conditioning data (Skoda native API)."""
        try:
            await self.set_token('connect')
            airconStatus = self.get(f'https://api.connect.skoda-auto.cz/api/v1/air-conditioning/{vin}/status')
            airconSettings = self.get(f'https://api.connect.skoda-auto.cz/api/v1/air-conditioning/{vin}/settings')
            airconData = await asyncio.gather(airconStatus, airconSettings)

            if airconData[0].get('state', {}):
                data = {'airConditioning': airconData[0]}
                if len(airconData) >= 2:
                    data['airConditioningSettings'] = airconData[1]
                if len(airconData) >= 3:
                    data['airConditioningTimers'] = airconData[2]
                _LOGGER.info(f"Returning with data {data}")
                return data
            elif airconData[0].get('status_code', False):
                _LOGGER.warning(f'Could not fetch air-conditioning data, HTTP status code: {airconData[0].get("status_code")}')
            elif airconData[1].get('status_code', False):
                _LOGGER.warning(f'Could not fetch air-conditioning settings, HTTP status code: {airconData[1].get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch air-conditioning data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch air-conditioning, error: {error}')
        return False

    async def getCharger(self, vin):
        """Get charger data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/batterycharge/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger'
                )
            )
            if response.get('charger', {}):
                data = {'charger': response.get('charger', {})}
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch charger, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch charger data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch charger, error: {error}')
        return False

    async def getCharging(self, vin):
        """Get charging data (New Skoda API)."""
        try:
            await self.set_token('connect')
            chargerStatus = self.get(f'https://api.connect.skoda-auto.cz/api/v1/charging/{vin}/status')
            chargerSettings = self.get(f'https://api.connect.skoda-auto.cz/api/v1/charging/{vin}/settings')
            chargingData = await asyncio.gather(chargerStatus, chargerSettings)

            if chargingData[0].get('battery', {}) or chargingData[1].get('maxChargeCurrentAc', {}):
                _LOGGER.debug(f'Got vehicle charging data')
                response = chargingData[0]
                response['chargerSettings'] = chargingData[1]
                return response
            elif chargerStatus.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch charging, HTTP status code: {chargerStatus.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch charging data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch charging, error: {error}')
        return False

    async def getPreHeater(self, vin):
        """Get parking heater data."""
        try:
            await self.set_token('vwg')
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    f'fs-car/bs/rs/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/status'
                )
            )
            if response.get('statusResponse', {}):
                data = {'heating': response.get('statusResponse', {})}
                return data
            elif response.get('status_code', {}):
                _LOGGER.warning(f'Could not fetch pre-heating, HTTP status code: {response.get("status_code")}')
            else:
                _LOGGER.info('Unhandled error while trying to fetch pre-heating data')
        except Exception as error:
            _LOGGER.warning(f'Could not fetch pre-heating, error: {error}')
        return False

 #### API data set functions ####
    async def get_request_status(self, vin, sectionId, requestId):
        """Return status of a request ID for a given section ID."""
        try:
            error_code = None
            # Requests for Skoda Native API
            if sectionId in ['charging',  'air-conditioning']:
                url = 'https://api.connect.skoda-auto.cz/api/v1/$sectionId/operation-requests/$requestId'
            # Requests for VW-Group API
            elif sectionId == 'climatisation':
                url = f'fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater/actions/$requestId'
            elif sectionId == 'batterycharge':
                url = f'fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger/actions/$requestId'
            elif sectionId == 'departuretimer':
                url = f'fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer/actions/$requestId'
            elif sectionId == 'vsr':
                url = f'fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests/$requestId/jobstatus'
            elif sectionId == 'rhf':
                url = f'fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/honkAndFlash/$requestId/status'
            else:
                url = f'fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests/$requestId/status'
            url = re.sub('\$sectionId', sectionId, url)
            url = re.sub('\$requestId', requestId, url)

            # Set token according to API origin
            if sectionId in ['charging', 'air-conditioning']:
                await self.set_token('connect')
            else:
                await self.set_token('vwg')

            response = await self.get(
                urljoin(
                    self._session_auth_ref_url,
                    url
                )
            )
            # Pre-heater on older cars
            if response.get('requestStatusResponse', {}).get('status', False):
                result = response.get('requestStatusResponse', {}).get('status', False)
            # Electric charging, climatisation and departure timers
            elif response.get('action', {}).get('actionState', False):
                result = response.get('action', {}).get('actionState', False)
                error_code = response.get('action', {}).get('errorCode', None)
            # Skoda native API requests
            elif response.get('status', False):
                result = response.get('status', False)
            else:
                result = 'Unknown'
            # Translate status messages to meaningful info
            if result in ['request_in_progress', 'queued', 'fetched', 'InProgress', 'Waiting']:
                status = 'In progress'
            elif result in ['request_fail', 'failed']:
                status = 'Failed'
                if error_code is not None:
                    # Identified error code for charging, 11 = not connected
                    if sectionId == 'charging' and error_code == 11:
                        _LOGGER.info(f'Request failed, charger is not connected')
                    else:
                        _LOGGER.info(f'Request failed with error code: {error_code}')
            elif result in ['unfetched', 'delayed', 'PollingTimeout']:
                status = 'No response'
            elif result in [ "FailPlugDisconnected", "FailTimerChargingActive" ]:
                status = "Unavailable"
            elif result in ['request_successful', 'succeeded', "Successful"]:
                status = 'Success'
            else:
                status = result
            return status
        except Exception as error:
            _LOGGER.warning(f'Failure during get request status: {error}')
            raise SkodaException(f'Failure during get request status: {error}')

    async def get_sec_token(self, vin, spin, action):
        """Get a security token, required for certain set functions."""
        urls = {
            'lock':    f'/api/rolesrights/authorization/v2/vehicles/{vin}/services/rlu_v1/operations/LOCK/security-pin-auth-requested',
            'unlock':  f'/api/rolesrights/authorization/v2/vehicles/{vin}/services/rlu_v1/operations/UNLOCK/security-pin-auth-requested',
            'heating': f'/api/rolesrights/authorization/v2/vehicles/{vin}/services/rheating_v1/operations/P_QSACT/security-pin-auth-requested',
            'timer':   f'/api/rolesrights/authorization/v2/vehicles/{vin}/services/timerprogramming_v1/operations/P_SETTINGS_AU/security-pin-auth-requested',
            'rclima':  f'/api/rolesrights/authorization/v2/vehicles/{vin}/services/rclima_v1/operations/P_START_CLIMA_AU/security-pin-auth-requested'
        }
        if not spin:
            raise SkodaConfigException('SPIN is required')
        try:
            await self.set_token('vwg')
            if not urls.get(action, False):
                raise SkodaException(f'Security token for "{action}" is not implemented')
            response = await self.get(
                urljoin(
                    self._session_spin_ref_url,
                    urls.get(action)
                )
            )
            secToken = response['securityPinAuthInfo']['securityToken']
            challenge = response['securityPinAuthInfo']['securityPinTransmission']['challenge']
            spinHash = self.hash_spin(challenge, str(spin))
            body = {
                'securityPinAuthentication': {
                    'securityPin': {
                        'challenge': challenge,
                        'securityPinHash': spinHash
                    },
                    'securityToken': secToken
                }
            }
            self._session_headers['Content-Type'] = 'application/json'
            response = await self.post(urljoin(self._session_spin_ref_url, '/api/rolesrights/authorization/v2/security-pin-auth-completed'), json = body)
            self._session_headers.pop('Content-Type', None)
            if response.get('securityToken', False):
                return response['securityToken']
            else:
                raise SkodaException('Did not receive a valid security token')
        except Exception as error:
            _LOGGER.error(f'Could not generate security token (maybe wrong SPIN?), error: {error}')
            raise

   # VW-Group API methods
    async def _setVWAPI(self, endpoint, **data):
        """Data call through VW-Group API."""
        try:
            await self.set_token('vwg')
            # Combine homeregion with endpoint URL
            url = urljoin(self._session_auth_ref_url, endpoint)
            response = await self._data_call(url, **data)
            self._session_headers.pop('X-mbbSecToken', None)
            self._session_headers.pop('X-securityToken', None)
            if not response:
                raise SkodaException(f'Invalid or no response for endpoint {endpoint}')
            elif response == 429:
                raise SkodaThrottledException('Action rate limit reached. Start the car to reset the action limit')
            else:
                data = {'id': '', 'state': ''}
                for key in response:
                    if isinstance(response.get(key), dict):
                        for k in response.get(key):
                            if 'id' in k.lower():
                                data['id'] = str(response.get(key).get(k))
                            if 'state' in k.lower():
                                data['state'] = response.get(key).get(k)
                    else:
                        if 'Id' in key:
                            data['id'] = str(response.get(key))
                        if 'State' in key:
                            data['state'] = response.get(key)
                if response.get('rate_limit_remaining', False):
                    data['rate_limit_remaining'] = response.get('rate_limit_remaining', None)
                return data
        except:
            self._session_headers.pop('X-mbbSecToken', None)
            self._session_headers.pop('X-securityToken', None)
            raise
        return False

    async def setCharger(self, vin, data):
        """Start/Stop charger."""
        return await self._setVWAPI(f'fs-car/bs/batterycharge/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger/actions', json = data)

    async def setClimater(self, vin, data, spin):
        """Execute climatisation actions."""
        try:
            # Only get security token if auxiliary heater is to be started
            if data.get('action', {}).get('settings', {}).get('heaterSource', None) == 'auxiliary':
                self._session_headers['X-securityToken'] = await self.get_sec_token(vin = vin, spin = spin, action = 'rclima')
            return await self._setVWAPI(f'fs-car/bs/climatisation/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater/actions', json = data)
        except:
            raise
        return False

    async def setDeparturetimer(self, vin, data, spin):
        """Set departure timers."""
        try:
            # First get most recent departuretimer settings from server
            departuretimers = await self.getDeparturetimer(vin)
            timer = departuretimers.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])
            profile = departuretimers.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])
            setting = departuretimers.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerBasicSetting', [])

            # Construct Timer data
            timers = [{},{},{}]
            for i in range(0, 3):
                timers[i]['currentCalendarProvider'] = {}
                for key in timer[i]:
                    # Ignore the timestamp key
                    if key not in ['timestamp']:
                        timers[i][key] = timer[i][key]
                if timers[i].get('timerFrequency', '') == 'single':
                    timers[i]['departureTimeOfDay'] = '00:00'

            # Set charger minimum limit if action is chargelimit
            if data.get('action', None) == 'chargelimit' :
                actiontype = 'setChargeMinLimit'
                setting['chargeMinLimit'] = int(data.get('limit', 50))
            # Modify timers if action is on, off or schedule
            elif data.get('action', None) in ['on', 'off', 'schedule']:
                actiontype = 'setTimersAndProfiles'
                if 'id' in data:
                    timerid = int(data.get('id', 1)) -1
                else:
                    timerid = int(data.get('schedule', {}).get('id', 1))-1

                # Set timer programmed status if data contains action = on or off
                if data.get('action', None) in ['on', 'off']:
                    action = 'programmed' if data.get('action', False) == 'on' else 'notProgrammed'
                # Set departure schedule
                elif data.get('action', None) == 'schedule':
                    action = 'programmed' if data.get('schedule', {}).get('enabled', False) else 'notProgrammed'
                    if data.get('schedule', {}).get('recurring', False):
                        timers[timerid]['timerFrequency'] = 'cyclic'
                        timers[timerid]['departureWeekdayMask'] = data.get('schedule', {}).get('days', 'nnnnnnn')
                        timers[timerid]['departureTimeOfDay'] = data.get('schedule', {}).get('time', '08:00')
                        timers[timerid].pop('departureDateTime', None)
                    else:
                        timers[timerid]['timerFrequency'] = 'single'
                        timers[timerid]['departureWeekdayMask'] = 'nnnnnnn'
                        timers[timerid]['departureTimeOfDay'] = '00:00'
                        timers[timerid]['departureDateTime'] = \
                            data.get('schedule', {}).get('date', '2020-01-01') + 'T' +\
                            data.get('schedule', {}).get('time', '08:00')
                # Catch uncatched scenario
                else:
                    action = 'notProgrammed'
                timers[timerid]['timerProgrammedStatus'] = action
            else:
                raise SkodaException('Unknown action for departure timer')

            # Construct Profiles data
            profiles = [{},{},{}]
            for i in range(0, 3):
                for key in profile[i]:
                    # Ignore the timestamp key
                    if key not in ['timestamp']:
                        profiles[i][key] = profile[i][key]

            # Set optional settings
            if data.get('schedule', {}).get('chargeMaxCurrent', None) is not None:
                profiles[timerid]['chargeMaxCurrent']=data.get('schedule', {}).get('chargeMaxCurrent',False)

            if data.get('schedule', {}).get('targetChargeLevel', None) is not None:
                profiles[timerid]['targetChargeLevel']=data.get('schedule', {}).get('targetChargeLevel',False)

            if data.get('schedule', {}).get('profileName', None) is not None:
                profiles[timerid]['profileName']=data.get('schedule', {}).get('profileName',False)

            if data.get('schedule', {}).get('operationClimatisation', None) is not None:
                profiles[timerid]['operationClimatisation']=data.get('schedule', {}).get('operationClimatisation',False)

            if data.get('schedule', {}).get('operationCharging', None) is not None:
                profiles[timerid]['operationCharging']=data.get('schedule', {}).get('operationCharging',False)

            # Construct basic settings
            settings = {
                'chargeMinLimit': int(setting['chargeMinLimit']),
                'heaterSource': 'electric',
                'targetTemperature': int(data['temp'])
            }
            body = {
                'action': {
                    'timersAndProfiles': {
                        'timerBasicSetting': settings,
                        'timerList': {
                            'timer': timers
                        },
                        'timerProfileList': {
                            'timerProfile': profiles
                        }
                    },
                    'type': actiontype
                }
            }
            await self.set_token('vwg')
            # Only get security token if auxiliary heater is to be enabled
            #if data.get... == 'auxiliary':
            #   self._session_headers['X-securityToken'] = await self.get_sec_token(vin = vin, spin = spin, action = 'timer')
            return await self._setVWAPI(f'fs-car/bs/departuretimer/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer/actions', json = body)
        except:
            raise
        return False

    async def setHonkAndFlash(self, vin, data):
        """Execute honk and flash actions."""
        return await self._setVWAPI(f'fs-car/bs/rhf/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/honkAndFlash', json = data)

    async def setLock(self, vin, data, spin):
        """Remote lock and unlock actions."""
        try:
            # Save Content-Type header to be restored later
            if 'Content-Type' in self._session_headers:
                contType = self._session_headers['Content-Type']
            else:
                contType = False
            # Fetch security token for lock/unlock
            if 'unlock' in data:
                self._session_headers['X-mbbSecToken'] = await self.get_sec_token(vin = vin, spin = spin, action = 'unlock')
            else:
                self._session_headers['X-mbbSecToken'] = await self.get_sec_token(vin = vin, spin = spin, action = 'lock')
            # Set temporary Content-Type
            self._session_headers['Content-Type'] = 'application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml'

            response = await self._setVWAPI(f'fs-car/bs/rlu/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/actions', data = data)

            # Clean up content-type
            self._session_headers.pop('Content-Type', None)
            if contType: self._session_headers['Content-Type'] = contType

            return response

        except:
            self._session_headers.pop('Content-Type', None)
            if contType: self._session_headers['Content-Type'] = contType
            raise
        return False

    async def setPreHeater(self, vin, data, spin):
        """Petrol/diesel parking heater actions."""
        try:
            if 'Content-Type' in self._session_headers:
                contType = self._session_headers['Content-Type']
            else:
                contType = ''
            self._session_headers['Content-Type'] = 'application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json'
            if isinstance(data, dict):
                if not 'quickstop' in data.get('performAction'):
                    self._session_headers['x-mbbSecToken'] = await self.get_sec_token(vin = vin, spin = spin, action = 'heating')
            else:
                raise SkodaConfigException("Invalid data for preheater")
            response = await self._setVWAPI(f'fs-car/bs/rs/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/action', json = data)

            # Clean up headers
            self._session_headers.pop('x-mbbSecToken', None)
            self._session_headers.pop('Content-Type', None)
            if contType: self._session_headers['Content-Type'] = contType

            return response

        except Exception as error:
            self._session_headers.pop('x-mbbSecToken', None)
            self._session_headers.pop('Content-Type', None)
            if contType: self._session_headers['Content-Type'] = contType
            raise
        return False

    async def setRefresh(self, vin):
        """"Force vehicle data update."""
        return await self._setVWAPI(f'fs-car/bs/vsr/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests', data=None)

   # Skoda native API request methods
    async def _setSkodaAPI(self, endpoint, vin, **data):
        """Data call through Skoda API."""
        try:
            await self.set_token('connect')
            url = f"https://api.connect.skoda-auto.cz/api/v1/{endpoint}/operation-requests?vin={vin}"
            response = await self._data_call(url, **data)
            if not response:
                raise SkodaException('Invalid or no response')
            else:
                request_id = response.get('id', 0)
                request_state = response.get('status', 'unknown')
                _LOGGER.debug(f'Request returned with state "{request_state}", request id: {request_id}')
                return dict({'id': str(request_id), 'state': request_state})
        except:
            raise
        return False

    async def setAirConditioning(self, vin, data):
        """Execute air conditioning actions."""
        return await self._setSkodaAPI('air-conditioning', vin, json = data)

    async def setTimers(self, vin, data):
        """Execute timer actions."""
        return await self._setSkodaAPI('air-conditioning', vin, json = data)

    async def setCharging(self, vin, data):
        """Execute charging actions."""
        return await self._setSkodaAPI('charging', vin, json = data)

 #### Token handling ####
    async def validate_token(self, token):
        """Function to validate a single token."""
        try:
            now = datetime.now()
            # Try old pyJWT syntax first
            try:
                exp = jwt.decode(token, verify=False).get('exp', None)
            except:
                exp = None
            # Try new pyJWT syntax if old fails
            if exp is None:
                try:
                    exp = jwt.decode(token, options={'verify_signature': False}).get('exp', None)
                except:
                    raise Exception("Could not extract exp attribute")

            expires = datetime.fromtimestamp(int(exp))

            # Lazy check but it's very inprobable that the token expires the very second we want to use it
            if expires > now:
                return expires
            else:
                _LOGGER.debug(f'Token expired at {expires.strftime("%Y-%m-%d %H:%M:%S")})')
                return False
        except Exception as e:
            _LOGGER.info(f'Token validation failed, {e}')
        return False

    async def verify_token(self, token):
        """Function to verify a single token."""
        try:
            req = None
            # Try old pyJWT syntax first
            try:
                aud = jwt.decode(token, verify=False).get('aud', None)
            except:
                aud = None
            # Try new pyJWT syntax if old fails
            if aud is None:
                try:
                    aud = jwt.decode(token, options={'verify_signature': False}).get('aud', None)
                except:
                    raise Exception("Could not extract exp attribute")

            if not isinstance(aud, str):
                aud = next(iter(aud))
            _LOGGER.debug(f"Verifying token for {aud}")
            # If audience indicates a client from https://identity.vwgroup.io
            for client in CLIENT_LIST:
                if self._session_fulldebug:
                    _LOGGER.debug(f"Matching {aud} against {CLIENT_LIST[client].get('CLIENT_ID', '')}")
                if aud == CLIENT_LIST[client].get('CLIENT_ID', ''):
                    req = await self._session.get(url = 'https://identity.vwgroup.io/oidc/v1/keys')
                    break

            # If no match for "Skoda" clients, assume token is issued from https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth
            if req is None:
                req = await self._session.get(url = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/public/jwk/v1')

            # Fetch key list
            keys = await req.json()
            pubkeys = {}
            # Convert all RSA keys and store in list
            for jwk in keys['keys']:
                kid = jwk['kid']
                if jwk['kty'] == 'RSA':
                    pubkeys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(to_json(jwk))
            # Get key ID from token and get match from key list
            token_kid = jwt.get_unverified_header(token)['kid']
            if self._session_fulldebug:
                try:
                    _LOGGER.debug(f'Token Key ID is {token_kid}, match from public keys: {keys["keys"][token_kid]}')
                except:
                    pass
            pubkey = pubkeys[token_kid]

            # Verify token with public key
            if jwt.decode(token, key=pubkey, algorithms=['RS256'], audience=aud):
                return True
        except ExpiredSignatureError:
            return False
        except Exception as error:
            _LOGGER.debug(f'Failed to verify {aud} token, error: {error}')
            return error

    async def refresh_token(self, client):
        """Function to refresh tokens for a client."""
        try:
            # Refresh API tokens
            _LOGGER.debug(f'Refreshing tokens for client "{client}"')
            if client in ['skoda', 'smartlink', 'connect']:
                body = {
                    'grant_type': 'refresh_token',
                    'brand': BRAND,
                    'refresh_token': self._session_tokens[client]['refresh_token']
                }
                url = 'https://tokenrefreshservice.apps.emea.vwapps.io/refreshTokens'
            else:
                body = {
                    'grant_type': 'refresh_token',
                    'scope': 'sc2:fal',
                    'token': self._session_tokens[client]['refresh_token']
                }
                url = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token'

            try:
                response = await self._session.post(
                    url=url,
                    headers=TOKEN_HEADERS.get(client),
                    data = body,
                )
            except:
                raise

            if response.status == 200:
                tokens = await response.json()
                # Verify access_token
                if 'access_token' in tokens:
                    if not await self.verify_token(tokens['access_token']):
                        _LOGGER.warning('Tokens could not be verified!')
                for token in tokens:
                    self._session_tokens[client][token] = tokens[token]
                return True
            elif response.status == 400:
                error = await response.json()
                if error.get('error', {}) == 'invalid_grant':
                    _LOGGER.debug(f'VW-Group API token refresh failed: {error.get("error_description", {})}')
                    if client == 'vwg':
                        return await self._getAPITokens()
            else:
                resp = await response.json()
                _LOGGER.warning(f'Something went wrong when refreshing tokens for "{client}".')
                _LOGGER.debug(f'Headers: {TOKEN_HEADERS.get("vwg")}')
                _LOGGER.debug(f'Request Body: {body}')
                _LOGGER.warning(f'Something went wrong when refreshing VW-Group API tokens.')
        except Exception as error:
            _LOGGER.warning(f'Could not refresh tokens: {error}')
        return False

    async def set_token(self, client):
        """Switch between tokens."""
        # Lock to prevent multiple instances updating tokens simultaneously
        async with self._lock:
            # If no tokens are available for client, try to authorize
            tokens = self._session_tokens.get(client, None)
            if tokens is None:
                _LOGGER.debug(f'Client "{client}" token is missing, call to authorize the client.')
                try:
                    # Try to authorize client and get tokens
                    if client != 'vwg':
                        result = await self._authorize(client)
                    else:
                        result = await self._getAPITokens()

                    # If authorization wasn't successful
                    if result is not True:
                        raise SkodaAuthenticationException(f'Failed to authorize client {client}')
                except:
                    raise
            try:
                # Validate access token for client, refresh if validation fails
                valid = await self.validate_token(self._session_tokens.get(client, {}).get('access_token', ''))
                if not valid:
                    _LOGGER.debug(f'Tokens for "{client}" are invalid')
                    # Try to refresh tokens for client
                    if await self.refresh_token(client) is not True:
                        raise SkodaTokenExpiredException(f'Tokens for client {client} are invalid')
                    else:
                        _LOGGER.debug(f'Tokens refreshed successfully for client "{client}"')
                        pass
                else:
                    try:
                        dt = datetime.fromtimestamp(valid)
                        _LOGGER.debug(f'Access token for "{client}" is valid until {dt.strftime("%Y-%m-%d %H:%M:%S")}')
                    except:
                        pass
                # Assign token to authorization header
                self._session_headers['Authorization'] = 'Bearer ' + self._session_tokens[client]['access_token']
                if client == 'skoda':
                    self._session_headers['tokentype'] = 'IDK_TECHNICAL'
                elif client == 'connect':
                    self._session_headers['tokentype'] = 'IDK_CONNECT'
                elif client == 'smartlink':
                    self._session_headers['tokentype'] = 'IDK_SMARTLINK'
                else:
                    self._session_headers['tokentype'] = 'MBB'
            except:
                raise SkodaException(f'Failed to set token for "{client}"')
            return True

 #### Class helpers ####
    @property
    def vehicles(self):
        """Return list of Vehicle objects."""
        return self._vehicles

    def vehicle(self, vin):
        """Return vehicle object for given vin."""
        return next(
            (
                vehicle
                for vehicle in self.vehicles
                if vehicle.unique_id.lower() == vin.lower()
            ), None
        )

    def hash_spin(self, challenge, spin):
        """Convert SPIN and challenge to hash."""
        spinArray = bytearray.fromhex(spin);
        byteChallenge = bytearray.fromhex(challenge);
        spinArray.extend(byteChallenge)
        return hashlib.sha512(spinArray).hexdigest()

async def main():
    """Main method."""
    if '-v' in argv:
        logging.basicConfig(level=logging.INFO)
    elif '-vv' in argv:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.ERROR)

    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        connection = Connection(session, **read_config())
        if await connection.doLogin():
            if await connection.get_vehicles():
                for vehicle in connection.vehicles:
                    print(f'Vehicle id: {vehicle}')
                    print('Supported sensors:')
                    for instrument in vehicle.dashboard().instruments:
                        print(f' - {instrument.name} (domain:{instrument.component}) - {instrument.str_state}')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
