# -*- coding: utf-8 -*-
"""
Communicate with MySkoda API.
Fork of https://github.com/skodaconnect/skodaconnect
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import random
import re
import secrets
import string
from base64 import b64encode
from datetime import datetime, timezone
from typing import Union
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import aiohttp
import jwt
from aiohttp import ClientSession, ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST
from bs4 import BeautifulSoup
from jwt.exceptions import ExpiredSignatureError

from myskoda.__version__ import __version__ as lib_version
from myskoda.exceptions import (
    SkodaAccountLockedException,
    SkodaAuthenticationException,
    SkodaConfigException,
    SkodaEULAException,
    SkodaException,
    SkodaInvalidRequestException,
    SkodaLoginFailedException,
    SkodaServiceUnavailable,
    SkodaThrottledException,
    SkodaTokenInvalidException,
)
from myskoda.utilities import json_loads
from myskoda.vehicle import Vehicle

from .const import (
    API_BASE,
    APP_URI,
    BASE_SESSION,
    BRAND,
    CLIENT_ID,
    COUNTRY,
    HEADERS_AUTH,
    HEADERS_SESSION,
    MODELAPI,
    MODELAPIKEY,
    MODELAPPID,
    MODELHOST,
    MODELVIEWL,
    MODELVIEWS,
    SCOPE,
    SYSTEM_ID,
    TIMEOUT_30S,
    TOKEN_HEADERS,
    TOKEN_TYPES,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class Connection:
    """Connection to MySkoda API."""

    def __init__(
        self, session: ClientSession, username: str, password: str, fulldebug=False
    ) -> None:
        self._session = session
        self._session_fulldebug = fulldebug
        self._session_headers = HEADERS_SESSION.copy()
        self._session_base = BASE_SESSION
        self._session_auth_headers = HEADERS_AUTH.copy()
        self._session_cookies = ""
        self._session_nonce = self._get_nonce()
        self._session_state = self._get_state()

        self._session_auth_ref_url = {"default": BASE_SESSION}
        self._session_spin_ref_url = {"default": BASE_SESSION}
        self._session_first_update = False
        self._session_auth_username = username
        self._session_auth_password = password
        self._vehicles = []
        self._session_tokens = {}

        _LOGGER.info(f"Unofficial MySkoda library, version {lib_version}")
        _LOGGER.debug(f"Using session {self._session_base}")

    def _clear_cookies(self) -> None:
        """Clear session cookies."""
        self._session._cookie_jar._cookies.clear()  # pylint: disable=protected-access
        self._session_cookies = ""

    def _get_nonce(self) -> str:
        """Return a valid nonce string."""
        chars = string.ascii_letters + string.digits
        text = "".join(secrets.choice(chars) for i in range(10))
        sha256 = hashlib.sha256()
        sha256.update(text.encode())
        return b64encode(sha256.digest()).decode("utf-8")[:-1]

    def _get_state(self):
        return self._get_nonce()

    async def restore_token(self, token: str) -> bool:
        """Try to restore refresh token."""
        try:
            _LOGGER.debug("Attempting restore saved token")
            expire = await self.validate_token(token)
            if not expire:
                raise Exception("Token expired")
            try:
                verified = await self.verify_token(token)
                if verified:
                    self._session_tokens = {"refresh_token": token}
                    _LOGGER.info(f"Restored token for, valid until {expire}")
                else:
                    raise SkodaTokenInvalidException("Token failed verification")
            except SkodaTokenInvalidException as err:
                _LOGGER.info(f"Token is invalid: {err}")
            except Exception as e:
                _LOGGER.debug(f"unhandled exception occured, error: {err}")
        except Exception as err:
            _LOGGER.debug(f"Token restore failed, error {err}")
            _LOGGER.info("Restore token failed")
            self._session_tokens = {}
            return False
        return True

    async def doLogin(self):
        """Login method, clean login"""
        _LOGGER.info("Initiating new login")

        if len(self._session_tokens) > 0:
            _LOGGER.info("Revoking old tokens.")
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
        self._session_nonce = self._get_nonce()
        self._session_state = self._get_state()

        # Login with skoda client
        return await self._authorize()

    async def _authorize(self):
        """Login method. Authorize and get tokens.

        TODO: refactor as this is way to long and complex
        """
        try:
            self._session_headers = HEADERS_SESSION.copy()
            self._session_auth_headers = HEADERS_AUTH.copy()

            _LOGGER.debug("Starting authorization process")
            req = await self._session.get(
                url="https://identity.vwgroup.io/.well-known/openid-configuration"
            )
            if req.status != 200:
                return False
            response_data = await req.json()
            auth_endpoint = response_data["authorization_endpoint"]
            auth_issuer = response_data["issuer"]
            verifier = "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
            verifier_hash = hashlib.sha256(verifier.encode("utf-8")).digest()
            challenge = (
                base64.b64encode(verifier_hash)
                .decode("utf-8")
                .replace("+", "-")
                .replace("/", "_")
                .rstrip("=")
            )
            url = (
                auth_endpoint
                + "?redirect_uri="
                + APP_URI
                + "&nonce="
                + self._session_nonce
                + "&state="
                + self._session_state
                + "&response_type="
                + TOKEN_TYPES
                + "&client_id="
                + CLIENT_ID
                + "&scope="
                + SCOPE
                + "&code_challenge="
                + challenge
                + "&code_challenge_method=s256"
                + "&prompt=login"
            )

            # Get authorization page (login page)
            if self._session_fulldebug:
                _LOGGER.debug(f'Get authorization page: "{auth_endpoint}"')
            try:
                req = await self._session.get(
                    url=url, headers=self._session_auth_headers, allow_redirects=False
                )
                if req.headers.get("Location", False):
                    ref = req.headers.get("Location", "")
                    if "error" in ref:
                        error = parse_qs(urlparse(ref).query).get("error", "")[0]
                        if "error_description" in ref:
                            error = parse_qs(urlparse(ref).query).get("error_description", "")[0]
                            _LOGGER.info(f"Unable to login, {error}")
                        else:
                            _LOGGER.info("Unable to login.")
                        raise SkodaException(error)
                    else:
                        if self._session_fulldebug:
                            _LOGGER.debug(f'Got authorization endpoint: "{ref}"')
                        req = await self._session.get(
                            url=ref,
                            headers=self._session_auth_headers,
                            allow_redirects=False,
                        )
                else:
                    _LOGGER.warning("Unable to fetch authorization endpoint")
                    raise SkodaException('Missing "location" header')
            except SkodaException:
                raise
            except Exception as error:
                _LOGGER.warning(f"Failed to get authorization endpoint. {error}")
                raise SkodaException(error)

            # If we need to sign in (first token)
            if "signin-service" in ref:
                _LOGGER.debug("User is not logged on, use signin service")
                location = await self._signin_service(req, auth_issuer, auth_endpoint)
            else:
                # We are already logged on, shorter authorization flow
                location = req.headers.get("Location", None)

            # Follow all redirects until we reach the callback URL
            try:
                ma_depth = 10
                while not location.startswith(APP_URI):
                    if location is None:
                        raise SkodaException("Login failed")
                    if self._session_fulldebug:
                        _LOGGER.debug(f'Process HTTP redirect URL "{location}"')
                    if "error" in location:
                        error = parse_qs(urlparse(location).query).get("error", "")[0]
                        if error == "login.error.throttled":
                            timeout = parse_qs(urlparse(location).query).get(
                                "enableNextButtonAfterSeconds", ""
                            )[0]
                            raise SkodaAccountLockedException(
                                f"Account is locked for another {timeout} seconds"
                            )
                        elif error == "login.errors.password_invalid":
                            raise SkodaAuthenticationException("Invalid password")
                        else:
                            _LOGGER.warning(f"Login failed: {error}")
                        raise SkodaLoginFailedException(error)
                    if "terms-and-conditions" in location:
                        raise SkodaEULAException(
                            "The terms and conditions must be accepted first at "
                            '"https://www.skoda-connect.com/"'
                        )

                    response = await self._session.get(
                        url=location,
                        headers=self._session_auth_headers,
                        allow_redirects=False,
                    )
                    if response.headers.get("Location", False) is False:
                        if "consent" in location:
                            new_form = await self._parse_form(response)
                            _LOGGER.info(
                                f"Consented scopes: "
                                f'{new_form.get("internalAndAlreadyConsentedScopes", "")}, not '
                                f'consented: {new_form.get("consentedScopes", "")}'
                            )
                            raise SkodaAuthenticationException(
                                f'Missing consent for scopes: {new_form.get("consentedScopes", "")}'
                            )
                        else:
                            raise SkodaAuthenticationException(
                                f"Unhandled error, redirect stopped at {location}"
                            )
                    location = response.headers.get("Location", None)
                    # Set a max limit on requests to prevent forever loop
                    ma_depth -= 1
                    if ma_depth == 0:
                        raise SkodaException("Too many redirects")
            except (
                SkodaException,
                SkodaEULAException,
                SkodaAuthenticationException,
                SkodaAccountLockedException,
                SkodaLoginFailedException,
            ):
                raise
            except Exception as err:
                # If we get an unhandled exception it should be because we can't redirect to the
                # APP_URI URL and thus we have our auth code
                if "code" in location:
                    if self._session_fulldebug:
                        _LOGGER.debug(f"Got code: {location}")
                    pass
                else:
                    _LOGGER.debug("Exception occured while logging in.")
                    raise SkodaLoginFailedException(err)

            _LOGGER.debug("Received authorization code, exchange for tokens.")
            # Extract code and tokens
            jwt_auth_code = parse_qs(urlparse(location).fragment).get("code")[0]
            token_body = {
                "code": jwt_auth_code,
                "redirectUri": "myskoda://redirect/login/",
                "verifier": verifier,
            }
            token_url = (
                f"{API_BASE}/api/v1/authentication/exchange-authorization-code?tokenType=CONNECT"
            )
            if self._session_fulldebug:
                _LOGGER.debug(f"Trying to authorize with {token_body}")
            new_header = {
                "Content-Type": "application/json; charset=UTF-8",
                "User-Agent": USER_AGENT,
            }
            req = await self._session.post(
                url=token_url,
                headers=new_header,
                json=token_body,
                allow_redirects=False,
            )
            _LOGGER.debug(f"Got {req}")
            if req.status != 200:
                if req.status >= 500:
                    raise SkodaServiceUnavailable(f"API returned HTTP status {req.status}")
                raise SkodaException(f"Token exchange failed. Request status: {req.status}")
            # Save access, identity and refresh tokens according to requested client
            _LOGGER.debug("Received token exchange response, checking for errors.")
            token_data = await req.json()
            if self._session_fulldebug:
                _LOGGER.debug(f"Token data is: {token_data}")
            self._session_tokens = {}

            # Assume that tokens were received OK
            if "error" not in token_data:
                self._session_tokens["access_token"] = token_data.get(
                    "access_token", token_data.get("accessToken", "")
                )
                self._session_tokens["refresh_token"] = token_data.get(
                    "refresh_token", token_data.get("refreshToken", "")
                )
                self._session_tokens["id_token"] = token_data.get(
                    "id_token", token_data.get("idToken", "")
                )
                self._session_headers["Authorization"] = (
                    "Bearer " + self._session_tokens["access_token"]
                )
            else:
                error = token_data.get("error", "")
                if "error_description" in token_data:
                    error_description = token_data.get("error_description", "")
                    raise SkodaException(f"{error} - {error_description}")
                else:
                    raise SkodaException(error)
            if self._session_fulldebug:
                for key in self._session_tokens:
                    _LOGGER.debug(f'Got {key}, token: "{self._session_tokens.get(key)}"')

            # Verify refresh token, warn if problems are found
            verified = await self.verify_token(self._session_tokens.get("refresh_token"))
            if verified is False:
                _LOGGER.warning("Token for is invalid!")
            elif isinstance(verified, dict):
                _LOGGER.info("Token verified OK.")
            else:
                _LOGGER.warning(f"Token could not be verified, verification returned {verified}.")
        except (
            SkodaEULAException,
            SkodaAccountLockedException,
            SkodaAuthenticationException,
            SkodaException,
            SkodaLoginFailedException,
        ) as err:
            _LOGGER.error(err)
            raise
        except TypeError:
            _LOGGER.warning(
                f"Login failed for {self._session_auth_username}. "
                "The server might be temporarily unavailable, try again later. "
                "If the problem persists, verify your account at https://www.skoda-connect.com"
            )
            raise
        except Exception as err:
            _LOGGER.error(f"Login failed for {self._session_auth_username}, {err}")
            raise SkodaLoginFailedException(error) from err
        return True

    async def _signin_service(self, html, auth_issuer, auth_endpoint):
        """Method to signin to MySkoda through forms."""
        try:
            user_form = await self._parse_form(html)
            # Expect first form to be HTML
            if user_form.get("type", None) == "html":
                user_form["email"] = self._session_auth_username
            else:
                raise SkodaAuthenticationException("Expected HTML data for initial login form!")
            if user_form.get("action", None) is not None:
                post_url = auth_issuer + user_form.get("action")
                user_form.pop("action", None)
            else:
                raise SkodaAuthenticationException("Could not find login URL!")
            form_data = user_form
            form_data.pop("type", None)
        except Exception:
            _LOGGER.error("Failed to extract user login form.")
            raise

        # POST email
        # https://identity.vwgroup.io/signin-service/v1/{CLIENT_ID}/login/identifier
        self._session_auth_headers["Referer"] = auth_endpoint
        self._session_auth_headers["Origin"] = auth_issuer
        _LOGGER.debug(f"Start login process for user {self._session_auth_username}")
        req = await self._session.post(
            url=post_url, headers=self._session_auth_headers, data=form_data
        )
        # Check valid response
        try:
            if req.status != 200:
                raise SkodaException(
                    "Authorization request failed, service might be temporarily unavailable."
                )
            if "error" in str(req.url):
                login_error = str(req.url).split("error=", 1)[1]
                if login_error == "validator.email.invalid":
                    raise SkodaConfigException(
                        f"Invalid email address provided: {self._session_auth_username}"
                    )
                else:
                    raise SkodaAuthenticationException(f"Login error: {login_error}")
        except (SkodaAuthenticationException, SkodaConfigException):
            raise
        except Exception as e:
            _LOGGER.debug(f"Unhandled error {e}")
            raise

        # Parse response and process data before posting password
        try:
            pw_form = await self._parse_form(req)
            if pw_form.get("type", "") == "html":
                _LOGGER.debug("Expected dynamic HTML form")
                if "register" in pw_form.get("action", ""):
                    raise SkodaLoginFailedException("The specified email is not registered")
            if pw_form.get("error", None) is not None:
                raise SkodaLoginFailedException(
                    f'Login failed with error: {pw_form.get("error", None)}'
                )
            if "registerCredentialsPath" in pw_form:
                raise SkodaAuthenticationException(
                    "Registration is not completed for this account!"
                )
            if not pw_form.get("hmac", False):
                raise SkodaLoginFailedException("Failed to extract login hmac attribute")
            if not pw_form.get("postAction", pw_form.get("action", False)):
                raise SkodaLoginFailedException("Failed to extract login post action attribute")
            form_data["hmac"] = pw_form.get("hmac", "")
            form_data["password"] = self._session_auth_password
            post_action = pw_form.get("postAction", pw_form.get("action", False))
        except SkodaLoginFailedException:
            raise
        except Exception as err:
            raise SkodaAuthenticationException(f"Login failed, error: {err}")

        # POST password
        # https://identity.vwgroup.io/signin-service/v1/{CLIENT_ID}/login/authenticate
        self._session_auth_headers["Referer"] = post_url
        self._session_auth_headers["Origin"] = auth_issuer
        _LOGGER.debug("Finalizing login")

        pw_post_url = auth_issuer + post_action
        if not "signin-service" in pw_post_url or not CLIENT_ID in pw_post_url:
            pw_post_url = auth_issuer + "/signin-service/v1/" + CLIENT_ID + "/" + post_action

        if self._session_fulldebug:
            _LOGGER.debug(f'Using login action url: "{pw_post_url}"')
        req = await self._session.post(
            url=pw_post_url,
            headers=self._session_auth_headers,
            data=form_data,
            allow_redirects=False,
        )

        return req.headers.get("Location", None)

    async def _parse_form(self, html):
        """Method to parse HTML form and return input values and action."""
        # Extract form and extract attributes
        try:
            form_data = {}
            response_data = await html.text()
            response_soup = BeautifulSoup(response_data, "html.parser")
            if response_soup is None:
                raise SkodaLoginFailedException(
                    "HTML form extraction failed, server did not return valid HTML data"
                )

            # There are two possibilities, either hard coded HTML form or dynamic form built by JS
            html_form = response_soup.find("form")
            js_scripts = response_soup.find_all("script", {"src": False})

            if html_form is not None:
                # Our form is built by HTML, extract input fields
                form_data["type"] = "html"
                _LOGGER.debug("Found HTML credentials form, extracting attributes")
                for field in html_form.find_all("input", type="hidden"):
                    if form_data.get(field["name"], False):
                        form_data[field["name"]] = form_data[field["name"]] + " " + field["value"]
                    else:
                        form_data[field["name"]] = field["value"]
                action = response_soup.find("form").get("action")
                if action is not None:
                    form_data["action"] = action
            elif js_scripts is not None:
                # Our form is dynamically built by javascript, extract JSON data
                form_data["type"] = "js"
                _LOGGER.debug("Found dynamic credentials form, extracting attributes")
                pattern = re.compile("templateModel: (.*?),\n")
                for script in js_scripts:
                    # Check all inline scripts and search for interesting data
                    if pattern.search(script.string):
                        data = pattern.search(script.string)
                        form_data = json.loads(data.groups()[0])
                        _LOGGER.debug(f"Script JSON data: {form_data}")
            else:
                raise SkodaLoginFailedException("Failed to extract login form data")
            if self._session_fulldebug:
                _LOGGER.debug(f"Extracted form attributes: {form_data}")
            return form_data
        except Exception as err:
            raise SkodaAuthenticationException(f"Failed to extract login form data, error {err}")

    async def terminate(self):
        """Log out from connect services"""
        _LOGGER.info("Initiating logout")
        await self.logout()

    async def logout(self):
        """Logout, revoke tokens."""
        try:
            refresh_token = self._session_tokens["refresh_token"]
            await self.revoke_token(refresh_token)
        except:
            _LOGGER.info("Some problem occured while revoking tokens, ignoring...")
            pass

    async def revoke_token(self, token):
        """Revoke refresh token for supplied client."""
        try:
            req_headers = TOKEN_HEADERS
            params = {
                "refreshToken": token,
            }
            revoke_url = (
                "https://mysmob.api.connect.skoda-auto.cz/api/v1/authentication/token/revoke?systemId="
                + SYSTEM_ID
            )
            if await self._session.post(revoke_url, headers=req_headers, data=params):
                _LOGGER.debug("Revocation of token successful")
                # Remove tokens from storage
                self._session_tokens = {}
                return True
            else:
                _LOGGER.warning("Revocation of token failed")
                return False
        except Exception as err:
            _LOGGER.info(f"Revocation of token failed with error: {err}")
        return False

    async def get(self, url: str):
        """Perform a HTTP GET."""
        try:
            response = await self._request(METH_GET, url)
            return response
        except aiohttp.client_exceptions.ClientResponseError as error:
            data = {
                "status_code": error.status,
                "error": error.code,
                "error_description": error.message,
                "response_headers": error.headers,
                "request_info": error.request_info,
            }
            if error.status == 401:
                _LOGGER.warning(
                    'Received "Unauthorized" while fetching data.\n'
                    "This can occur if tokens expired or refresh service is unavailable."
                )
            elif error.status == 400:
                _LOGGER.error(
                    'Received "Bad Request" from server.\n'
                    "The request might be malformed or not implemented correctly for this vehicle."
                )
            elif error.status == 412:
                _LOGGER.debug(
                    'Received "Pre-condition failed".\n' "Service might be temporarily unavailable."
                )
            elif error.status == 500:
                _LOGGER.info(
                    'Received "Internal server error".\n' "The service is temporarily unavailable."
                )
            elif error.status == 502:
                _LOGGER.info(
                    'Received "Bad gateway".\n'
                    "Either the endpoint is temporarily unavailable or not supported for this vehicle."
                )
            elif 400 <= error.status <= 499:
                _LOGGER.error(
                    "Received unhandled error indicating client-side problem.\n"
                    "Restart or try again later."
                )
            elif 500 <= error.status <= 599:
                _LOGGER.error(
                    "Received unhandled error indicating server-side problem.\n"
                    "The service might be temporarily unavailable."
                )
            else:
                _LOGGER.error("Received unhandled error while requesting API endpoint.")
            _LOGGER.debug(f"HTTP request information: {data}")
            return data
        except Exception as err:
            _LOGGER.debug(f"Got non HTTP related error: {err}")

    async def post(self, url: str, **data):
        """Perform a HTTP POST."""
        if data:
            return await self._request(METH_POST, url, **data)
        return await self._request(METH_POST, url)

    async def _request(self, method: str, url: str, **kwargs):
        """Perform a HTTP request."""
        if self._session_fulldebug:
            _LOGGER.debug(f'HTTP {method} "{url}"')
        async with self._session.request(
            method,
            url,
            headers=self._session_headers,
            timeout=ClientTimeout(total=TIMEOUT_30S.seconds),
            cookies=self._session_cookies,
            raise_for_status=False,
            **kwargs,
        ) as response:
            response.raise_for_status()

            # Update cookie jar
            if self._session_cookies != "":
                self._session_cookies.update(response.cookies)
            else:
                self._session_cookies = response.cookies

            try:
                if response.status == 204:
                    res = {"status_code": response.status}
                elif response.status >= 200 or response.status <= 300:
                    # If this is a revoke token url, expect Content-Length 0 and return
                    if int(response.headers.get("Content-Length", 0)) == 0 and "revoke" in url:
                        if response.status == 200:
                            return True
                        else:
                            return False
                    else:
                        res = await response.json(loads=json_loads)
                else:
                    res = {}
                    _LOGGER.debug(
                        f"Not success status code [{response.status}] response: {response}"
                    )
                if "X-RateLimit-Remaining" in response.headers:
                    res["rate_limit_remaining"] = response.headers.get("X-RateLimit-Remaining", "")
            except Exception as err:
                res = {}
                _LOGGER.debug(
                    f"Something went wrong [{response.status}] response: {response}, error: {err}"
                )
                return res

            if self._session_fulldebug:
                _LOGGER.debug(
                    f'Request for "{url}" returned with status code [{response.status}], response: {res}'
                )
            else:
                _LOGGER.debug(f'Request for "{url}" returned with status code [{response.status}]')
            return res

    async def _data_call(self, query: str, **data):
        """Function for POST actions with error handling."""
        try:
            response = await self.post(query, **data)
            _LOGGER.debug(f"Data call returned: {response}")
            return response
        except aiohttp.client_exceptions.ClientResponseError as err:
            _LOGGER.debug(
                f"Request failed. Data: {data}, HTTP request headers: {self._session_headers}"
            )
            if err.status == 401:
                _LOGGER.error("Unauthorized")
            elif err.status == 400:
                _LOGGER.error("Bad request")
            elif err.status == 429:
                _LOGGER.warning(
                    "Too many requests. Further requests can only be made after the end of next trip in order to protect your vehicles battery."
                )
                return 429
            elif err.status == 500:
                _LOGGER.error("Internal server error, server might be temporarily unavailable")
            elif err.status == 502:
                _LOGGER.error("Bad gateway, this function may not be implemented for this vehicle")
            else:
                _LOGGER.error(f"Unhandled HTTP exception: {err}")
            # return False
        except Exception as err:
            _LOGGER.error(f"Failure to execute: {err}")
        return False

    # Class get data functions
    async def update_all(self):
        """Update status."""
        try:
            # Get all Vehicle objects and update in parallell
            update_list = []
            for vehicle in self.vehicles:
                if vehicle.vin not in update_list:
                    _LOGGER.debug(f"Adding {vehicle.vin} for data refresh")
                    update_list.append(vehicle.update())
                else:
                    _LOGGER.debug(f"VIN {vehicle.vin} is already queued for data refresh")

            # Wait for all data updates to complete
            if len(update_list) == 0:
                _LOGGER.info("No vehicles in account to update")
            else:
                _LOGGER.debug("Calling update function for all vehicles")
                await asyncio.gather(*update_list)
            return True
        except (IOError, OSError, LookupError, Exception) as err:
            _LOGGER.warning(f"An error was encountered during interaction with the API: {err}")
        return False

    async def get_vehicles(self):
        """Fetch vehicle information from user profile."""
        skoda_vehicles = []

        # Authorize for "skoda" client and get vehicles from garage endpoint
        response = await self.get("https://mysmob.api.connect.skoda-auto.cz/api/v2/garage")
        # Check that response is a list
        # if isinstance(response, list):
        if isinstance(response.get("vehicles", None), list):
            # skoda_vehicles = response
            skoda_vehicles = response.get("vehicles")

        # If neither API returns any vehicles, raise an error
        if len(skoda_vehicles) == 0:
            raise SkodaConfigException("No vehicles were found for given account!")

        # Get vehicle connectivity information
        else:
            try:
                for vehicle in skoda_vehicles:
                    _LOGGER.debug(f"Checking vehicle {vehicle}")
                    vin = vehicle.get("vin", "")
                    # response = await self.get(
                    #     f"https://mysmob.api.connect.skoda-auto.cz/api/v1/vehicle-information/{vin}"
                    # )
                    response = await self.get(
                        f"https://mysmob.api.connect.skoda-auto.cz/api/v2/garage/vehicles/{vin}"
                    )
                    specification = response["specification"]
                    capabilities = response["capabilities"]["capabilities"]

                    # TODO: Remove? Looks like connecities is no longer a thing with the new API
                    # connectivity = []
                    # for service in vehicle.get("connectivities", []):
                    #     if isinstance(service, str):
                    #         connectivity.append(service)
                    #     elif isinstance(service, dict):
                    #         connectivity.append(service.get("type", ""))

                    # capabilities = []
                    # for capability in vehicle.get("capabilities", {}).get(
                    #     "capabilities", []
                    # ):
                    #     capabilities.append(capability.get("id", ""))

                    vehicle = {
                        "vin": vin,
                        # "connectivities": connectivity,
                        "capabilities": capabilities,
                        "specification": specification,
                    }

                    # Check if object already exist
                    _LOGGER.debug("Check if vehicle exists")
                    if self.vehicle(vin) is not None:
                        _LOGGER.debug(f"Vehicle with VIN number {vin} already exist.")
                        car = Vehicle(self, vehicle)
                        if not car == self.vehicle(vehicle):
                            _LOGGER.debug(f"Updating {vehicle} object")
                            self._vehicles.pop(vehicle)
                            self._vehicles.append(Vehicle(self, vehicle))
                    else:
                        _LOGGER.debug(f"Adding vehicle {vin}, with capabilities: {capabilities}")
                        self._vehicles.append(Vehicle(self, vehicle))
            except:
                raise SkodaLoginFailedException("Unable to fetch associated vehicles for account")
        return skoda_vehicles

    # Vehicle related functions
    async def getHomeRegion(self, vin: str):
        """Get API requests base url for VIN."""
        try:
            response = await self.get(
                f"https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion"
            )
            self._session_auth_ref_url[vin] = (
                response["homeRegion"]["baseUri"]["content"]
                .split("/api")[0]
                .replace("mal-", "fal-")
                if response["homeRegion"]["baseUri"]["content"]
                != "https://mal-1a.prd.ece.vwg-connect.com/api"
                else "https://msg.volkswagen.de"
            )
            self._session_spin_ref_url[vin] = response["homeRegion"]["baseUri"]["content"].split(
                "/api"
            )[0]
            return response["homeRegion"]["baseUri"]["content"]
        except Exception as err:
            _LOGGER.debug(f"Could not get homeregion, error {err}")
            self._session_auth_ref_url[vin] = self._session_auth_ref_url["default"]
            self._session_spin_ref_url[vin] = self._session_spin_ref_url["default"]
        return False

    async def getOperationList(self, vin: str):
        """Collect operationlist for VIN, supported/licensed functions."""
        try:
            response = await self.get(
                urljoin(
                    self._session_spin_ref_url[vin],
                    f"/api/rolesrights/operationlist/v3/vehicles/{vin}",
                )
            )
            if response.get("operationList", False):
                data = response.get("operationList", {})
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch operation list, HTTP status code: {response.get("status_code")}'
                )
                data = response
            else:
                _LOGGER.info(f"Could not fetch operation list: {response}")
                data = {"error": "unknown"}
        except Exception as err:
            _LOGGER.warning(f"Could not fetch operation list, error: {err}")
            data = {"error": "unknown"}
        return data

    async def get_model_image_url(self, vin: str, size: str):
        """Construct the URL for the model image."""
        try:
            # Construct message to be encrypted
            date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%mZ")
            if size in ["S", "s", "Small", "small"]:
                message = (
                    MODELAPPID
                    + "\n"
                    + MODELAPI
                    + "?vin="
                    + vin
                    + "&view="
                    + MODELVIEWS
                    + "&date="
                    + date
                )
            else:
                message = (
                    MODELAPPID
                    + "\n"
                    + MODELAPI
                    + "?vin="
                    + vin
                    + "&view="
                    + MODELVIEWL
                    + "&date="
                    + date
                )
            # Construct hmac SHA-256 key object and encode the message
            digest = hmac.new(MODELAPIKEY, msg=message.encode(), digestmod=hashlib.sha256).digest()
            b64enc = {"sign": b64encode(digest).decode()}
            sign = urlencode(b64enc)
            # Construct the URL
            if size in ["S", "s", "Small", "small"]:
                path = (
                    MODELAPI
                    + "?vin="
                    + vin
                    + "&view="
                    + MODELVIEWS
                    + "&appId="
                    + MODELAPPID
                    + "&date="
                    + date
                    + "&"
                    + sign
                )
            else:
                path = (
                    MODELAPI
                    + "?vin="
                    + vin
                    + "&view="
                    + MODELVIEWL
                    + "&appId="
                    + MODELAPPID
                    + "&date="
                    + date
                    + "&"
                    + sign
                )
            url = MODELHOST + path
            try:
                response = await self._session.get(url=url, allow_redirects=False)
                if response.headers.get("Location", False):
                    return response.headers.get("Location").split("?")[0]
                else:
                    _LOGGER.debug(
                        "Could not fetch Model image URL, request returned with status code {response.status_code}"
                    )
            except:
                _LOGGER.debug("Could not fetch Model image URL")
        except:
            _LOGGER.debug("Could not fetch Model image URL, message signing failed.")
        return None

    async def get_vehicle_status_report(self, vin: str):
        """Get stored vehicle status report (Connect services)."""
        try:
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/vsr/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/status",
                )
            )
            if (
                response.get("StoredVehicleDataResponse", {})
                .get("vehicleData", {})
                .get("data", {})[0]
                .get("field", {})[0]
            ):
                data = {
                    "StoredVehicleDataResponse": response.get("StoredVehicleDataResponse", {}),
                    "StoredVehicleDataResponseParsed": dict(
                        [
                            (e["id"], e if "value" in e else "")
                            for f in [
                                s["field"]
                                for s in response["StoredVehicleDataResponse"]["vehicleData"][
                                    "data"
                                ]
                            ]
                            for e in f
                        ]
                    ),
                }
                return data
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch vehicle status report, HTTP status code: {response.get("status_code")}'
                )
            else:
                _LOGGER.info("Unhandled error while trying to fetch status data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch StoredVehicleDataResponse, error: {err}")
        return False

    async def get_vehicle_status(self, vin: str, smartlink=False):
        """Get stored vehicle status (SmartLink and new API).

        TODO: only need one function probably?
        """
        try:
            if smartlink:
                response = await self.get(
                    f"https://mysmob.api.connect.skoda-auto.cz/api/v1/vehicle-status/{vin}"
                )
                if response:
                    data = {"vehicle_status": response}
                    return data
                elif response.get("status_code", {}):
                    _LOGGER.warning(
                        f'Could not fetch vehicle status, HTTP status code: {response.get("status_code")}'
                    )
                else:
                    _LOGGER.info(
                        "Unhandled error while trying to fetch vehicle status via SmartLink"
                    )
            else:
                response = await self.get(
                    f"https://mysmob.api.connect.skoda-auto.cz/api/v1/vehicle-health-report/warning-lights/{vin}"
                )
                if response:
                    data = {"vehicle_remote": response.get("remote", {})}
                    # Check for errors
                    if len(response.get("errors", [])) > 0:
                        data["errors"] = response.get("errors", [])
                    return data
                elif response.get("status_code", {}):
                    _LOGGER.warning(
                        f'Could not fetch vehicle status, HTTP status code: {response.get("status_code")}'
                    )
                else:
                    _LOGGER.info(
                        "Unhandled error while trying to fetch vehicle status via SmartLink"
                    )
        except Exception as err:
            _LOGGER.warning(f"Could not fetch SmartLink vehicle status, error: {err}")
        return False

    async def get_trip_statistics(self, vin: str):
        """Get short term trip statistics."""
        try:
            short = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/tripstatistics/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/tripdata/shortTerm?newest",
                )
            )
            long = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/tripstatistics/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/tripdata/longTerm?newest",
                )
            )
            cyclic = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/tripstatistics/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/tripdata/cyclic?newest",
                )
            )
            data = {}
            if short.get("tripData", False):
                data["tripstatistics"] = short.get("tripData", {})
            else:
                _LOGGER.warning(
                    f"Could not fetch shortterm trip statistics, HTTP status code: "
                    f'{short.get("status_code", "none")}'
                )
            if long.get("tripData", False):
                data["longtermstatistics"] = long.get("tripData", {})
            else:
                _LOGGER.warning(
                    f"Could not fetch longterm trip statistics, HTTP status code: "
                    f'{long.get("status_code", "none")}'
                )
            if cyclic.get("tripData", False):
                data["cyclicstatistics"] = cyclic.get("tripData", {})
            else:
                _LOGGER.warning(
                    f"Could not fetch cyclic trip statistics, HTTP status code: "
                    f'{cyclic.get("status_code", "none")}'
                )
            return data
        except Exception as err:
            _LOGGER.warning(f"Could not fetch trip statistics, error: {err}")
        return False

    async def get_position(self, vin):
        """Get position data.

        TODO:  old, no longer used?
        """
        try:
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/cf/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/position",
                )
            )
            if response.get("findCarResponse", {}):
                data = {
                    "findCarResponse": response.get("findCarResponse", {}),
                    "isMoving": False,
                }
                return data
            elif response.get("status_code", {}):
                if response.get("status_code", 0) == 204:
                    _LOGGER.debug("Seems car is moving, HTTP 204 received from position")
                    data = {"isMoving": True, "rate_limit_remaining": 15}
                    return data
                else:
                    _LOGGER.warning(
                        f'Could not fetch position, HTTP status code: {response.get("status_code")}'
                    )
            else:
                _LOGGER.info("Unhandled error while trying to fetch positional data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch position, error: {err}")
        return False

    async def get_parking_position(self, vin):
        """Get position data."""
        try:
            # response = await self.get(
            #     f"https://mysmob.api.connect.skoda-auto.cz/api/v1/position/vehicles/{vin}/parking-position"
            # )
            response = await self.get(
                f"https://mysmob.api.connect.skoda-auto.cz/api/v1/maps/positions?vin={vin}"
            )
            # TODO: just keeping same response dict with 'findCarResponse' for now, but no reason
            # it has to be like this ....
            if gps_coord := response.get("positions")[0].get("gpsCoordinates"):
                data = {"findCarResponse": gps_coord, "isMoving": False}
                return data
            elif response.get("status_code", {}):
                if response.get("status_code", 0) == 204:
                    _LOGGER.debug("Seems car is moving, HTTP 204 received from position")
                    data = {"isMoving": True}
                    return data
                else:
                    _LOGGER.warning(
                        f'Could not fetch position, HTTP status code: {response.get("status_code")}'
                    )
            else:
                _LOGGER.info("Unhandled error while trying to fetch positional data")
        except Exception as error:
            _LOGGER.warning(f"Could not fetch position, error: {error}")
        return False

    async def get_departure_timer(self, vin: str):
        """Get departure timers."""
        try:
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/departuretimer/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer",
                )
            )
            if response.get("timer", {}):
                data = {"departuretimer": response.get("timer", {})}
                return data
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch timers, HTTP status code: {response.get("status_code")}'
                )
            else:
                _LOGGER.info("Unknown error while trying to fetch data for departure timers")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch timers, error: {err}")
        return False

    # AC timers are now included in the single api/v2/air-conditioning/VIN calls
    # async def get_timers(self, vin: str):
    #     """Get timers data."""
    #     try:
    #         response = await self.get(
    #             f"https://mysmob.api.connect.skoda-auto.cz/api/v1/air-conditioning/{vin}/timers"
    #         )
    #         if response.get("timers", []):
    #             data = {"timers": response.get("timers", [])}
    #             return data
    #         elif response.get("status_code", False):
    #             _LOGGER.warning(
    #                 f'Could not fetch timers, HTTP status code: {response.get("status_code")}'
    #             )
    #         else:
    #             _LOGGER.info("Unhandled error while trying to fetch timers data")
    #     except Exception as err:
    #         _LOGGER.warning(f"Could not fetch timers, error: {err}")
    #     return False

    async def get_climater(self, vin):
        """Get climatisation data."""
        try:
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/climatisation/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater",
                )
            )
            if response.get("climater", {}):
                data = {"climater": response.get("climater", {})}
                return data
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch climatisation, HTTP status code: {response.get("status_code")}'
                )
            else:
                _LOGGER.info("Unhandled error while trying to fetch climatisation data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch climatisation, error: {err}")
        return False

    async def get_air_conditioning(self, vin):
        """Get air-conditioning data."""
        try:
            response = await self.get(
                f"https://mysmob.api.connect.skoda-auto.cz/api/v2/air-conditioning/{vin}"
            )
            # aircon_status = self.get(
            #     f"https://mysmob.api.connect.skoda-auto.cz/api/v1/air-conditioning/{vin}/status"
            # )
            # aircon_settings = self.get(
            #     f"https://mysmob.api.connect.skoda-auto.cz/api/v1/air-conditioning/{vin}/settings"
            # )
            # aircon_data = await asyncio.gather(aircon_status, aircon_settings)

            if response.get("state"):
                return response
            _LOGGER.warning(
                f'Could not fetch air-conditioning data, HTTP status code: {response.get("status_code")}'
            )
            # if aircon_data[0].get("state", {}):
            #     data = {"airConditioning": aircon_data[0]}
            #     if len(aircon_data) >= 2:
            #         data["airConditioningSettings"] = aircon_data[1]
            #     _LOGGER.info(f"Returning with data {data}")
            #     return data
            # elif aircon_data[0].get("status_code", False):
            #     _LOGGER.warning(
            #         f'Could not fetch air-conditioning data, HTTP status code: {aircon_data[0].get("status_code")}'
            #     )
            # elif aircon_data[1].get("status_code", False):
            #     _LOGGER.warning(
            #         f'Could not fetch air-conditioning settings, HTTP status code: {aircon_data[1].get("status_code")}'
            #     )
            # else:
            #     _LOGGER.info("Unhandled error while trying to fetch air-conditioning data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch air-conditioning, error: {err}")
        return False

    async def get_charger(self, vin: str):
        """Get charger data."""
        try:
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/batterycharge/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger",
                )
            )
            if response.get("charger", {}):
                data = {"charger": response.get("charger", {})}
                return data
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch charger, HTTP status code: {response.get("status_code")}'
                )
            else:
                _LOGGER.info("Unhandled error while trying to fetch charger data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch charger, error: {err}")
        return False

    async def get_charging(self, vin):
        """Get charging data."""
        try:
            response = await self.get(
                f"https://mysmob.api.connect.skoda-auto.cz/api/v1/charging/{vin}"
            )
            charging_status = response["status"]
            charging_settings = response["settings"]

            if charging_status.get("battery", {}) or charging_settings.get(
                "maxChargeCurrentAc", {}
            ):
                response = charging_status
                response["chargerSettings"] = charging_settings
                return response
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch charging, HTTP status code: {response.get("status_code")}'
                )
            else:
                _LOGGER.info("Unhandled error while trying to fetch charging data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch charging, error: {err}")
        return False

    async def get_pre_heater(self, vin: str):
        """Get parking heater data."""
        try:
            response = await self.get(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/rs/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/status",
                )
            )
            if response.get("statusResponse", {}):
                data = {"heating": response.get("statusResponse", {})}
                return data
            elif response.get("status_code", {}):
                _LOGGER.warning(
                    f'Could not fetch pre-heating, HTTP status code: {response.get("status_code")}'
                )
            else:
                _LOGGER.info("Unhandled error while trying to fetch pre-heating data")
        except Exception as err:
            _LOGGER.warning(f"Could not fetch pre-heating, error: {err}")
        return False

    #### API data set functions ####
    async def get_request_status(self, vin: str, section_id: str, request_id: str):
        """Return status of a request ID for a given section ID."""
        try:
            error_code = None
            # Requests for Skoda Native API
            if section_id in ["charging", "air-conditioning"]:
                url = "https://mysmob.api.connect.skoda-auto.cz/api/v1/$sectionId/operation-requests/$requestId"
            # Requests for VW-Group API
            elif section_id == "climatisation":
                url = urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater/actions/$requestId",
                )
            elif section_id == "batterycharge":
                url = urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger/actions/$requestId",
                )
            elif section_id == "departuretimer":
                url = urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer/actions/$requestId",
                )
            elif section_id == "vsr":
                url = urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests/$requestId/jobstatus",
                )
            elif section_id == "rhf":
                url = urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/honkAndFlash/$requestId/status",
                )
            else:
                url = urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/$sectionId/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests/$requestId/status",
                )
            url = re.sub(r"\$sectionId", section_id, url)
            url = re.sub(r"\$requestId", request_id, url)

            response = await self.get(url)

            # Pre-heater on older cars
            if response.get("requestStatusResponse", {}).get("status", False):
                result = response.get("requestStatusResponse", {}).get("status", False)
            # Electric charging, climatisation and departure timers
            elif response.get("action", {}).get("actionState", False):
                result = response.get("action", {}).get("actionState", False)
                error_code = response.get("action", {}).get("errorCode", None)
            # Skoda native API requests
            elif response.get("status", False):
                result = response.get("status", False)
            else:
                result = "Unknown"
            # Translate status messages to meaningful info
            if result in [
                "request_in_progress",
                "queued",
                "fetched",
                "InProgress",
                "Waiting",
            ]:
                status = "In progress"
            elif result in ["request_fail", "failed"]:
                status = "Failed"
                if error_code is not None:
                    # Identified error code for charging, 11 = not connected
                    if section_id == "charging" and error_code == 11:
                        _LOGGER.info("Request failed, charger is not connected")
                    else:
                        _LOGGER.info(f"Request failed with error code: {error_code}")
            elif result in ["unfetched", "delayed", "PollingTimeout"]:
                status = "No response"
            elif result in ["FailPlugDisconnected", "FailTimerChargingActive"]:
                status = "Unavailable"
            elif result in ["request_successful", "succeeded", "Successful"]:
                status = "Success"
            else:
                status = result
            return status
        except Exception as err:
            _LOGGER.warning(f"Failure during get request status: {err}")
            raise SkodaException(f"Failure during get request status: {err}")

    async def get_sec_token(self, vin: str, spin: str, action: str):
        """Get a security token, required for certain set functions."""
        urls = {
            "lock": f"/api/rolesrights/authorization/v2/vehicles/{vin}/services/rlu_v1/operations/LOCK/security-pin-auth-requested",
            "unlock": f"/api/rolesrights/authorization/v2/vehicles/{vin}/services/rlu_v1/operations/UNLOCK/security-pin-auth-requested",
            "heating": f"/api/rolesrights/authorization/v2/vehicles/{vin}/services/rheating_v1/operations/P_QSACT/security-pin-auth-requested",
            "timer": f"/api/rolesrights/authorization/v2/vehicles/{vin}/services/timerprogramming_v1/operations/P_SETTINGS_AU/security-pin-auth-requested",
            "rclima": f"/api/rolesrights/authorization/v2/vehicles/{vin}/services/rclima_v1/operations/P_START_CLIMA_AU/security-pin-auth-requested",
        }
        if not spin:
            raise SkodaConfigException("SPIN is required")
        try:
            if not urls.get(action, False):
                raise SkodaException(f'Security token for "{action}" is not implemented')
            response = await self.get(urljoin(self._session_spin_ref_url[vin], urls.get(action)))
            sec_token = response["securityPinAuthInfo"]["securityToken"]
            challenge = response["securityPinAuthInfo"]["securityPinTransmission"]["challenge"]
            spin_hash = self.hash_spin(challenge, str(spin))
            body = {
                "securityPinAuthentication": {
                    "securityPin": {
                        "challenge": challenge,
                        "securityPinHash": spin_hash,
                    },
                    "securityToken": sec_token,
                }
            }
            self._session_headers["Content-Type"] = "application/json"
            response = await self.post(
                urljoin(
                    self._session_spin_ref_url[vin],
                    "/api/rolesrights/authorization/v2/security-pin-auth-completed",
                ),
                json=body,
            )
            self._session_headers.pop("Content-Type", None)
            if response.get("securityToken", False):
                return response["securityToken"]
            else:
                raise SkodaException("Did not receive a valid security token")
        except Exception as err:
            _LOGGER.error(f"Could not generate security token (maybe wrong SPIN?), error: {err}")
            raise

    # VW-Group API methods
    async def _setVWAPI(self, url, **data):
        """Data call through VW-Group API.

        TODO: old VW API, no longer used?
        """
        try:
            # Combine homeregion with endpoint URL
            # url = urljoin(self._session_auth_ref_url, endpoint)
            response = await self._data_call(url, **data)
            self._session_headers.pop("X-mbbSecToken", None)
            self._session_headers.pop("X-securityToken", None)
            if not response:
                # raise SkodaException(f'Invalid or no response for endpoint {endpoint}')
                raise SkodaException(f"Invalid or no response for endpoint {url}")
            elif response == 429:
                raise SkodaThrottledException(
                    "Action rate limit reached. Start the car to reset the action limit"
                )
            else:
                data = {"id": "", "state": ""}
                for key in response:
                    if isinstance(response.get(key), dict):
                        for k in response.get(key):
                            if "id" in k.lower():
                                data["id"] = str(response.get(key).get(k))
                            if "state" in k.lower():
                                data["state"] = response.get(key).get(k)
                    else:
                        if "Id" in key:
                            data["id"] = str(response.get(key))
                        if "State" in key:
                            data["state"] = response.get(key)
                if response.get("rate_limit_remaining", False):
                    data["rate_limit_remaining"] = response.get("rate_limit_remaining", None)
                return data
        except:
            self._session_headers.pop("X-mbbSecToken", None)
            self._session_headers.pop("X-securityToken", None)
            raise

    async def setCharger(self, vin, data):
        """Start/Stop charger.

        TODO: old VW API, no longer used?
        """
        return await self._setVWAPI(
            urljoin(
                self._session_auth_ref_url[vin],
                f"fs-car/bs/batterycharge/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger/actions",
            ),
            json=data,
        )

    async def setClimater(self, vin, data, spin):
        """Execute climatisation actions.

        TODO: old VW API, no longer used?
        """
        try:
            # Only get security token if auxiliary heater is to be started
            if data.get("action", {}).get("settings", {}).get("heaterSource", None) == "auxiliary":
                self._session_headers["X-securityToken"] = await self.get_sec_token(
                    vin=vin, spin=spin, action="rclima"
                )
            return await self._setVWAPI(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/climatisation/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater/actions",
                ),
                json=data,
            )
        except:
            raise
        return False

    async def setDeparturetimer(self, vin, data, spin):
        """Set departure timers.

        TODO: old VW API, no longer used?
        """
        try:
            # First get most recent departuretimer settings from server
            departuretimers = await self.get_departure_timer(vin)
            timer = (
                departuretimers.get("departuretimer", {})
                .get("timersAndProfiles", {})
                .get("timerList", {})
                .get("timer", [])
            )
            profile = (
                departuretimers.get("departuretimer", {})
                .get("timersAndProfiles", {})
                .get("timerProfileList", {})
                .get("timerProfile", [])
            )
            setting = (
                departuretimers.get("departuretimer", {})
                .get("timersAndProfiles", {})
                .get("timerBasicSetting", {})
            )
            # Set heater source according to settings
            source = (
                departuretimers.get("departuretimer", {})
                .get("timersAndProfiles", {})
                .get("timerBasicSetting", {})
                .get("heaterSource", "electric")
            )

            # Construct Timer data
            timers = [{}, {}, {}]
            for i in range(0, 3):
                timers[i]["currentCalendarProvider"] = {}
                for key in timer[i]:
                    # Ignore the timestamp key
                    if key not in ["timestamp"]:
                        timers[i][key] = timer[i][key]
                if timers[i].get("timerFrequency", "") == "single":
                    timers[i]["departureTimeOfDay"] = "00:00"

            # Set charger minimum limit if action is chargelimit
            if data.get("action", None) == "chargelimit":
                actiontype = "setChargeMinLimit"
                setting["chargeMinLimit"] = int(data.get("limit", 50))
            # Modify timers if action is on, off or schedule
            elif data.get("action", None) in ["on", "off", "schedule"]:
                actiontype = "setTimersAndProfiles"
                if "id" in data:
                    timerid = int(data.get("id", 1)) - 1
                else:
                    timerid = int(data.get("schedule", {}).get("id", 1)) - 1

                # Set timer programmed status if data contains action = on or off
                if data.get("action", None) in ["on", "off"]:
                    action = "programmed" if data.get("action", False) == "on" else "notProgrammed"
                # Set departure schedule
                elif data.get("action", None) == "schedule":
                    action = (
                        "programmed"
                        if data.get("schedule", {}).get("enabled", False)
                        else "notProgrammed"
                    )
                    if data.get("schedule", {}).get("recurring", False):
                        timers[timerid]["timerFrequency"] = "cyclic"
                        timers[timerid]["departureWeekdayMask"] = data.get("schedule", {}).get(
                            "days", "nnnnnnn"
                        )
                        timers[timerid]["departureTimeOfDay"] = data.get("schedule", {}).get(
                            "time", "08:00"
                        )
                        timers[timerid].pop("departureDateTime", None)
                    else:
                        timers[timerid]["timerFrequency"] = "single"
                        timers[timerid]["departureWeekdayMask"] = "nnnnnnn"
                        timers[timerid]["departureTimeOfDay"] = "00:00"
                        timers[timerid]["departureDateTime"] = (
                            data.get("schedule", {}).get("date", "2020-01-01")
                            + "T"
                            + data.get("schedule", {}).get("time", "08:00")
                        )
                # Catch uncatched scenario
                else:
                    action = "notProgrammed"
                timers[timerid]["timerProgrammedStatus"] = action

            # If heatersource is to be set
            elif data.get("action", None) == "heaterSource":
                actiontype = "setTimersAndProfiles"

            else:
                raise SkodaException("Unknown action for departure timer")

            # Set heatersource from data, if specified
            if data.get("heaterSource", "") in ["automatic", "electric"]:
                source = data.get("heaterSource")

            # Construct Profiles data
            enabled = None
            profiles = [{}, {}, {}]
            for i in range(0, 3):
                for key in profile[i]:
                    # Ignore the timestamp key
                    if key not in ["timestamp"]:
                        profiles[i][key] = profile[i][key]
                # Set heater source
                profiles[i]["heaterSource"] = source
                if timers[i].get("timerProgrammedStatus", None) == "programmed":
                    enabled = True

            if enabled == None and source == "automatic":
                raise SkodaInvalidRequestException(
                    "At least one departure must be scheduled for heater to be enabled"
                )

            # Set optional settings
            if data.get("schedule", {}).get("chargeMaxCurrent", None) is not None:
                profiles[timerid]["chargeMaxCurrent"] = data.get("schedule", {}).get(
                    "chargeMaxCurrent", False
                )

            if data.get("schedule", {}).get("targetChargeLevel", None) is not None:
                profiles[timerid]["targetChargeLevel"] = data.get("schedule", {}).get(
                    "targetChargeLevel", False
                )

            if data.get("schedule", {}).get("profileName", None) is not None:
                profiles[timerid]["profileName"] = data.get("schedule", {}).get(
                    "profileName", False
                )

            if data.get("schedule", {}).get("operationClimatisation", None) is not None:
                profiles[timerid]["operationClimatisation"] = data.get("schedule", {}).get(
                    "operationClimatisation", False
                )

            if data.get("schedule", {}).get("operationCharging", None) is not None:
                profiles[timerid]["operationCharging"] = data.get("schedule", {}).get(
                    "operationCharging", False
                )

            # Construct basic settings
            settings = {
                "chargeMinLimit": int(setting["chargeMinLimit"]),
                "heaterSource": source,
                "targetTemperature": int(data["temp"]),
            }
            body = {
                "action": {
                    "timersAndProfiles": {
                        "timerBasicSetting": settings,
                        "timerList": {"timer": timers},
                        "timerProfileList": {"timerProfile": profiles},
                    },
                    "type": actiontype,
                }
            }

            # Only get security token if auxiliary heater is to be enabled
            if source == "automatic":
                self._session_headers["X-securityToken"] = await self.get_sec_token(
                    vin=vin, spin=spin, action="timer"
                )

            # return await self._setVWAPI(
            return await self._setVWAPI(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/departuretimer/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer/actions",
                ),
                json=body,
            )
        except:
            raise
        return False

    async def setHonkAndFlash(self, vin, data):
        """Execute honk and flash actions.

        TODO: old VW API, no longer used?
        """
        # return await self._setVWAPI(
        return await self._setVWAPI(
            urljoin(
                self._session_auth_ref_url[vin],
                f"fs-car/bs/rhf/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/honkAndFlash",
            ),
            json=data,
        )

    async def setLock(self, vin, data, spin):
        """Remote lock and unlock actions.

        TODO: old VW API, no longer used?
        """
        try:
            # Save Content-Type header to be restored later
            if "Content-Type" in self._session_headers:
                contType = self._session_headers["Content-Type"]
            else:
                contType = False
            # Fetch security token for lock/unlock
            if "unlock" in data:
                self._session_headers["X-mbbSecToken"] = await self.get_sec_token(
                    vin=vin, spin=spin, action="unlock"
                )
            else:
                self._session_headers["X-mbbSecToken"] = await self.get_sec_token(
                    vin=vin, spin=spin, action="lock"
                )
            # Set temporary Content-Type
            self._session_headers["Content-Type"] = (
                "application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml"
            )

            response = await self._setVWAPI(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/rlu/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/actions",
                ),
                data=data,
            )

            # Clean up content-type
            self._session_headers.pop("Content-Type", None)
            if contType:
                self._session_headers["Content-Type"] = contType

            return response

        except:
            self._session_headers.pop("Content-Type", None)
            if contType:
                self._session_headers["Content-Type"] = contType
            raise
        return False

    async def setPreHeater(self, vin, data, spin):
        """Petrol/diesel parking heater actions.

        TODO: old VW API, no longer used?
        """
        try:
            if "Content-Type" in self._session_headers:
                contType = self._session_headers["Content-Type"]
            else:
                contType = ""
            self._session_headers["Content-Type"] = (
                "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"
            )
            if isinstance(data, dict):
                if not "quickstop" in data.get("performAction"):
                    self._session_headers["x-mbbSecToken"] = await self.get_sec_token(
                        vin=vin, spin=spin, action="heating"
                    )
            else:
                raise SkodaConfigException("Invalid data for preheater")
            response = await self._setVWAPI(
                urljoin(
                    self._session_auth_ref_url[vin],
                    f"fs-car/bs/rs/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/action",
                ),
                json=data,
            )

            # Clean up headers
            self._session_headers.pop("x-mbbSecToken", None)
            self._session_headers.pop("Content-Type", None)
            if contType:
                self._session_headers["Content-Type"] = contType

            return response

        except Exception as error:
            self._session_headers.pop("x-mbbSecToken", None)
            self._session_headers.pop("Content-Type", None)
            if contType:
                self._session_headers["Content-Type"] = contType
            raise
        return False

    async def setRefresh(self, vin):
        """ "Force vehicle data update.

        TODO: old VW API, no longer used?
        """
        return await self._setVWAPI(
            urljoin(
                self._session_auth_ref_url[vin],
                f"fs-car/bs/vsr/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests",
            ),
            data=None,
        )

    async def setWindowHeater(self, vin, action):
        """Special handling of window heater for native API.

        TODO: old VW API, no longer used?
        """
        try:
            if action in ["start", "stop"]:
                url = f"https://mysmob.api.connect.skoda-auto.cz/api/v1/air-conditioning/operation-requests/{action}-window-heating"
                body = {"vin": vin}
            else:
                raise SkodaInvalidRequestException("Invalid action for window heating.")
            response = await self._data_call(url, json=body)
            if not response:
                _LOGGER.debug(f"API call failed, data: {body}")
                raise SkodaException("Invalid or no response")
            else:
                request_id = response.get("id", 0)
                request_state = response.get("status", "unknown")
                _LOGGER.debug(
                    f'Request returned with state "{request_state}", request id: {request_id}'
                )
                return dict({"id": str(request_id), "state": request_state})
        except:
            raise

    # Skoda native API request methods
    async def _set_skoda_api(self, endpoint: str, vin: str, **data):
        """Data call through Skoda API.

        TODO: refactor
        """
        url = f"https://mysmob.api.connect.skoda-auto.cz/api/v1/{endpoint}/operation-requests?vin={vin}"
        response = await self._data_call(url, **data)
        if not response:
            _LOGGER.debug(f"API call failed, data: {data}")
            raise SkodaException("Invalid or no response")
        else:
            request_id = response.get("id", 0)
            request_state = response.get("status", "unknown")
            _LOGGER.debug(
                f'Request returned with state "{request_state}", request id: {request_id}'
            )
            return dict({"id": str(request_id), "state": request_state})

    async def set_air_conditioning(self, vin, data):
        """Execute air conditioning actions."""
        return await self._set_skoda_api("air-conditioning", vin, json=data)

    async def set_timers(self, vin, data):
        """Execute timer actions.

        TODO: nothing is calling this?"""
        return await self._set_skoda_api("air-conditioning", vin, json=data)

    async def set_charging(self, vin: str, data: dict):
        """Execute charging actions."""
        return await self._set_skoda_api("charging", vin, json=data)

    #### Token handling ####
    def decode_token(self, token: str):
        """Helper method to deocde jwt token, different syntax in different versions."""
        # Try old pyJWT syntax first
        try:
            decoded = jwt.decode(token, verify=False)
        except:
            decoded = None
        # Try new pyJWT syntax if old fails
        if decoded is None:
            try:
                decoded = jwt.decode(token, options={"verify_signature": False})
            except:
                decoded = None
        if decoded is None:
            raise SkodaTokenInvalidException("Failed to decode token")
        else:
            return decoded

    async def validate_token(self, token: str):
        """Function to validate a single token."""
        try:
            now = datetime.now()
            exp = self.decode_token(token).get("exp", None)
            expires = datetime.fromtimestamp(int(exp))

            # Lazy check but it's very inprobable that the token expires the very second we want to use it
            if expires > now:
                return expires
            else:
                _LOGGER.debug(f'Token expired at {expires.strftime("%Y-%m-%d %H:%M:%S")})')
                return False
        except Exception as err:
            _LOGGER.info(f"Token validation failed, {err}")
        return False

    async def verify_token(self, token: str) -> Union[str, dict]:
        """Function to verify a refresh token.

        TODO: The return values of this method are ... questionable.
        """
        if token is None:
            raise SkodaTokenInvalidException('Invalid token "None"')
        try:
            req = None
            decoded = self.decode_token(token)

            # Verify that token type is either refresh_token for 'Skoda' or RT for VW-Group
            if decoded.get("typ", decoded.get("jtt", None)) not in [
                "RT",
                "refresh_token",
            ]:
                raise SkodaTokenInvalidException("Invalid refresh token")

            aud = decoded.get("aud", None)
            if aud is None:
                raise SkodaTokenInvalidException("Missing audience attribute")
            if not isinstance(aud, str):
                aud = next(iter(aud))

            _LOGGER.debug(f"Matching token audience {aud} to client ID")
            try:
                if aud != CLIENT_ID:
                    raise SkodaTokenInvalidException("Token audience does not match the client ID")
                if self._session_fulldebug:
                    _LOGGER.debug("Audience and client ID matches, fetching JWKs")
                req = await self._session.get(url="https://identity.vwgroup.io/oidc/v1/keys")
            except Exception as err:
                _LOGGER.debug(f"Received error {err} while trying to match")
                raise

            # Fetch key list
            keys = await req.json()
            pubkeys = {}
            # Convert all RSA keys and store in list
            for jwk in keys["keys"]:
                kid = jwk["kid"]
                if jwk["kty"] == "RSA":
                    pubkeys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            # Get key ID from token and get match from key list
            token_kid = jwt.get_unverified_header(token)["kid"]
            if self._session_fulldebug:
                _LOGGER.debug(f"Token Key ID is {token_kid}, match from public keys: {pubkeys}")
            pubkey = pubkeys[token_kid]

            verified = jwt.decode(token, key=pubkey, algorithms=["RS256"], audience=aud)
            if verified and self._session_fulldebug:
                _LOGGER.debug("Successfully verified refresh token audience and signature")
            return verified
        except SkodaTokenInvalidException as err:
            return err
        except ExpiredSignatureError:
            return False
        except Exception as err:
            _LOGGER.debug(f"Failed to verify {aud} token, error: {err}")
            return err

    async def refresh_token(self):
        """Function to refresh tokens."""
        try:
            # Refresh API tokens
            _LOGGER.debug("Refreshing tokens")
            old_token = self._session_tokens["refresh_token"]
            payload = {"json": {"refreshToken": old_token}}
            url = "https://mysmob.api.connect.skoda-auto.cz/api/v1/authentication/refresh-token?tokenType=CONNECT"
            try:
                response = await self._session.post(
                    url=url,
                    headers=TOKEN_HEADERS,
                    **payload,
                )
            except Exception as e:
                _LOGGER.debug(f"Token refresh failed: {e}")
                raise

            if response.status == 200:
                tokens = await response.json()
                if not "error" in tokens:
                    _LOGGER.debug("Refresh tokens succeeded, revoking old refresh tokens")
                    try:
                        await self.revoke_token(old_token)
                    except:
                        _LOGGER.warning("Token revocation failed!")
                    # Get and store tokens in common naming format
                    self._session_tokens["access_token"] = tokens.get(
                        "access_token", tokens.get("accessToken")
                    )
                    self._session_tokens["refresh_token"] = tokens.get(
                        "refresh_token", tokens.get("refreshToken")
                    )
                    self._session_tokens["id_token"] = tokens.get("id_token", tokens.get("idToken"))
                    self._session_headers["Authorization"] = (
                        "Bearer " + self._session_tokens["access_token"]
                    )
                else:
                    error = tokens.get("error", "")
                    if "error_description" in tokens:
                        error_description = tokens.get("error_description", "")
                        raise SkodaException(f"{error} - {error_description}")
                    else:
                        raise SkodaException(error)
                return True
            elif response.status == 400:
                error = await response.json()
                _LOGGER.debug(error)
                if error.get("error", {}) in [
                    "invalid_grant",
                    "unsupported_grant_type",
                ]:
                    _LOGGER.debug(f'API token refresh failed: {error.get("error_description", {})}')
                else:
                    _LOGGER.debug(f"Response JSON: {error}")
                    raise SkodaException("Failed token refresh")
            else:
                _LOGGER.warning("Something went wrong when refreshing tokens")
                _LOGGER.debug(f"Response: {response}")
        except Exception as err:
            _LOGGER.warning(f"Could not refresh tokens: {err}")
        return False

    #### Class helpers ####
    @property
    def vehicles(self) -> list[Vehicle]:
        """Return list of Vehicle objects."""
        return self._vehicles

    def vehicle(self, vin):
        """Return vehicle object for given vin."""
        return next(
            (vehicle for vehicle in self.vehicles if vehicle.unique_id.lower() == vin.lower()),
            None,
        )

    def hash_spin(self, challenge: str, spin: str):
        """Convert SPIN and challenge to hash."""
        spin_array = bytearray.fromhex(spin)
        byte_challenge = bytearray.fromhex(challenge)
        spin_array.extend(byte_challenge)
        return hashlib.sha512(spin_array).hexdigest()
