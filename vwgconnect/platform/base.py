#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abstract base class for API clients.
Models methods and properties needed for the different APIs.
"""

from __future__ import annotations
from typing import Union, Optional
import hashlib
import hmac
from base64 import b64encode
from urllib.parse import parse_qs, urlparse, urlencode, urljoin
from datetime import timedelta, datetime, timezone
from abc import ABC, abstractmethod
from jwt.exceptions import DecodeError
import asyncio
from aiohttp import ClientSession, ClientTimeout
from vwgconnect.helper.html import parse_form
from vwgconnect.helper.token import token_valid, decode_token
from vwgconnect.string.globals import (
    ACCESS_TOKEN,
    ID_TOKEN,
    REFRESH_TOKEN,
    REVOKE,
    REFRESH,
    ACCESSTOKEN,
    IDTOKEN,
    REFRESHTOKEN,
    AUTHZ_CODE,
    AUTHZ_ENDPOINT,
    CODE,
    ISSUER,
    SYSID,
    SUBJECT,
    CONSENT,
    CONSENT_SCOPES,
    HTTP_GET,
    HTTP_POST,
    HTTP_OK,
    HTTP_EMPTY,
    HTTP_MOVED,
    HTTP_REDIR,
    HTTP_OTHER,
    STATUS,
    DATA,
    JSON,
    PARAMS,
    LOCATION,
    URL,
    CONTENT,
    REFERER,
    ORIGIN,
    APP_JSON,
    TYPE,
    HTML,
    ACTION,
    JS,
    EMAIL,
    PASSWORD,
    APP_FORM,
    POST_ACTION,
    XREQ_WITH,
    TIMEOUT,
    OPENID_URL,
    SKODA_TOKEN,
    VIN,
    REGISTER,
    TERMS,
    HMAC,
    CRED_PATH,
    SIGNIN_SERVICE,
    SSO,
    V1,
    ERROR,
    ERROR_DESC,
    ERRORS,
    ERROR_DEFAULT,
    MODELAPI,
    MODELURL,
    MODELAPPID,
    MODELAPIKEY,
    SMALL,
    LARGE,
    IMAGESIZE,
    VIEW,
    DATE,
    SIGN,
    APPID,
    NEWLINE,
)


class APIClient(ABC):
    """Base class for API interactions."""

    def __init__(
        self: APIClient,
        http_session: ClientSession,
        cookies: any = "",
        api_debug: bool = False,
    ) -> None:
        """
        Init API Client

        Arguments:
            http_session: class, aiohttp session
            api_debug: bool, enable response debugs
        """
        self._session = http_session
        self._tokens = dict()
        self._lock = asyncio.Lock()
        self._session_debug = api_debug
        self._session_cookies = cookies

        # Client specific variables, set through child class objects
        self.redirect_uri = str
        self.response_type = str
        self.client_id = str
        self.system_id = str
        self.scope = str
        self.auth_params = dict
        self.auth_headers = dict
        self.app_name = str

    # Properties of class instance
    @property
    def subject(self: APIClient) -> Union(str, None):
        """Return subject claim from JWT access token."""
        try:
            token_claims = decode_token(self.access_token)
            return token_claims.get(SUBJECT, None)
        except DecodeError:
            return None

    @property
    def id_token(self: APIClient) -> Union(str, None):
        """Return Identity Token."""
        try:
            return self._tokens.get(ID_TOKEN, None)
        except TypeError:
            return None

    @id_token.setter
    def id_token(self: APIClient, token: str) -> None:
        """
        Set ID token.
        Parameters:
            token: token string
        """
        if not token_valid(token):
            raise Exception("Invalid id token")
        if isinstance(token, str):
            self._tokens[ID_TOKEN] = token

    @property
    def access_token(self: APIClient) -> Union(str, None):
        """Return Access Token."""
        try:
            return self._tokens.get(ACCESS_TOKEN, None)
        except TypeError:
            return None

    @access_token.setter
    def access_token(self: APIClient, token: str) -> None:
        """
        Set Access token.
        Parameters:
            token: token string
        """
        if not token_valid(token):
            raise Exception("Invalid access token")
        if isinstance(token, str):
            self._tokens[ACCESS_TOKEN] = token

    @property
    def refresh_token(self: APIClient) -> Union(str, None):
        """Return Refresh Token."""
        try:
            return self._tokens.get(REFRESH_TOKEN, None)
        except TypeError:
            return None

    @refresh_token.setter
    def refresh_token(self: APIClient, token: str) -> None:
        """
        Set Refresh token.
        Parameters:
            token: token string
        """
        if not token_valid(token):
            raise Exception("Invalid refresh token")
        if isinstance(token, str):
            self._tokens[REFRESH_TOKEN] = token

    # Inherited methods, same for all children
    async def _request(
        self: APIClient,
        url: str,
        headers: Optional[dict] = None,
        method: str = HTTP_GET,
        redirect: bool = True,
        **payload: dict,
    ) -> dict:
        """
        API GET HTTP call.

        Parameters:
            url: HTTP URL to send GET request to.
            headers: Optional. HTTP headers to use for HTTP request.
            method: Optional. HTTP method, defaults to 'GET'.
            redirect: Optional. Follow redirects or not, defaults to True.

            payload: Optional. dict with 'json': {}, 'params': {} or 'data': {}

        Returns:
            dict:
                status: HTTP status code
                data:   HTTP data object, if data exist else None
                location:   HTTP location header if exists
                url:    HTTP URL
        """
        data = {STATUS: 0, DATA: None, LOCATION: None, URL: None}
        try:
            async with self._session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=ClientTimeout(total=timedelta(seconds=TIMEOUT).seconds),
                #                cookies = self._session_cookies,
                allow_redirects=redirect,
                raise_for_status=False,
                **payload,
            ) as response:
                response.raise_for_status()
                data[STATUS] = response.status
                data[URL] = str(response.url)
                if response.status in [HTTP_MOVED, HTTP_REDIR, HTTP_OTHER]:
                    data[LOCATION] = response.headers.get(LOCATION, None)
                else:
                    if response.headers.get(CONTENT, None) == APP_JSON:
                        data[DATA] = await response.json()
                    else:
                        data[DATA] = await response.text()
        except Exception as exc:  # pylint: disable=broad-except
            data[STATUS] = 0
            data[ERROR] = str(exc)
        return data

    async def _get_oidconfig(self: APIClient) -> Union(dict, bool):
        """Fetch OpenID Configuration. Return dict with config."""
        try:
            # Fetch OpenID configuration
            oid_resp = await self._request(url=OPENID_URL)
            if oid_resp.get(STATUS) is HTTP_OK:
                return oid_resp.get(DATA, None)
        except Exception:  # pylint: disable=broad-except
            pass
        return False

    async def _signin(
        self: APIClient, html: str, username: str, password: str, issuer: str, endpoint: str
    ) -> Union(str, bool):
        """
        POST login credentials to signin form. Return authz redirect URL.
        Parameters:
            html: HTML data containing login form.
            username: Email address for account.
            password: Password for account.
            issuer: issuer from OIDC config.
            endpoint: authorization_endpoint from OIDC config.
        """
        # Parse login form and prepare POST data
        try:
            form_data = parse_form(html)
            # Validate form contents
            if not isinstance(form_data, dict):
                raise Exception("Unrecognized HTML login form")
            if form_data.get(TYPE, None) is not HTML:
                raise Exception("Expected HTML data for login form!")
            if form_data.get(ACTION, None) is None:
                raise Exception("Could not extract login URL.")

            # Populate login form data
            form_data[EMAIL] = username
            post_url = issuer + form_data.get(ACTION)
            form_data.pop(ACTION, None)
            form_data.pop(TYPE, None)
        except Exception as exc:
            raise Exception("Failed to extract user login form.") from exc

        # POST login form data and validate response
        try:
            email_resp = await self._request(
                url=post_url,
                headers={
                    CONTENT: APP_FORM,
                    XREQ_WITH: self.app_name,
                    REFERER: endpoint,
                    ORIGIN: issuer,
                },
                method=HTTP_POST,
                data=form_data,
            )
            url = email_resp.get(URL, "")
            if email_resp.get(STATUS, 0) is not HTTP_OK:
                raise Exception("Authentication failed.")
            if ERROR in url:
                login_error = str(url).split("error=", 1)[1]
                raise Exception(login_error)
            if email_resp.get(ERROR, False):
                raise Exception(email_resp.get(ERROR))
        except Exception as exc:
            raise Exception(f"Login POST email request failed. {exc}") from exc

        # Parse password form and prepare POST data
        try:
            pw_form = parse_form(email_resp.get(DATA))
            # Validate form contents
            if pw_form.get(TYPE, "") is not JS:
                if REGISTER in pw_form.get(ACTION, ""):
                    raise Exception("The email address is not registered.")
            if pw_form.get(ERROR, None) is not None:
                raise Exception(pw_form.get(ERROR, None))
            if CRED_PATH in pw_form:
                raise Exception("Registration is not completed for this email.")
            if not pw_form.get(HMAC, False):
                raise Exception("Failed to extract hmac attribute")
            if not pw_form.get(POST_ACTION, pw_form.get(ACTION, False)):
                raise Exception("Failed to extract action URL from login form.")

            # Add new hmac and password to form data
            form_data[HMAC] = pw_form.get("hmac")
            form_data[PASSWORD] = password
            pw_action = pw_form.get(POST_ACTION, pw_form.get(ACTION))
        except Exception as exc:
            raise Exception(f"Failed login, error: {exc}") from exc

        # POST password form data and validate respone
        try:
            pw_post = issuer + pw_action
            if SIGNIN_SERVICE not in pw_post or self.client_id not in pw_post:
                parts = [issuer, SIGNIN_SERVICE, V1, self.client_id, pw_action]
                pw_post = "/".join(parts)

            pw_resp = await self._request(
                url=pw_post,
                headers={
                    CONTENT: APP_FORM,
                    XREQ_WITH: self.app_name,
                    REFERER: post_url,
                    ORIGIN: issuer,
                },
                method=HTTP_POST,
                data=form_data,
                redirect=False,
            )
            location = pw_resp.get(LOCATION, "")
            if SSO not in location:
                raise Exception("Unexpected response after login")
        except Exception as exc:
            raise Exception("Login failed. {exc}") from exc

        return location

    async def _authorize(self: APIClient, redirect_url: str) -> str:
        """
        Authorization of client.
        Follow authorization URL through all redirects until Class redirect_uri
        is reached. Returns string: authorization code.
        """
        try:
            max_depth = 10
            # Loop until callback URL is reached
            while not redirect_url.startswith(self.redirect_uri):
                # Validate URL first so there's no errors
                if redirect_url is None:
                    raise Exception("Login failed")
                if ERROR in redirect_url:
                    error = parse_qs(urlparse(redirect_url).query).get(ERROR, "")[0]
                    raise Exception(ERRORS.get(error, ERROR_DEFAULT))
                if TERMS in redirect_url:
                    raise Exception("Accept EULA in MySkoda app on Android.")

                # Follow next redirect and error check response
                response = await self._request(url=redirect_url, redirect=False)
                if not response.get(LOCATION, False):
                    if CONSENT in redirect_url:
                        form = await parse_form(response.get(DATA, ""))
                        raise Exception(
                            f"Missing consent for scopes: \
                            {form.get(CONSENT_SCOPES, '')}"
                        )
                    raise Exception(f"Unhandled error at {redirect_url}")
                redirect_url = response.get(LOCATION, None)

                # Set a max limit on requests to prevent redirect loop
                max_depth -= 1
                if max_depth == 0:
                    raise Exception("Too many redirects")
        except Exception as exc:  # pylint: disable=broad-except
            # When redirect_uri is reached an Exception will occur
            # since the URL will be non http:// or https://
            if CODE not in redirect_url:
                raise Exception("No athorization code received.") from exc
        # Validate received authorization code
        try:
            code = parse_qs(urlparse(redirect_url).fragment).get(CODE)[0]
            if not len(code) > 0 or not isinstance(code, str):
                raise Exception("Received invalid authorization code.")
            return code
        except Exception as exc:
            raise Exception from exc

    async def auth(self: APIClient, email: str, password: str) -> bool:
        """Login/Authorize the client and return tokens."""
        oid_config = await self._get_oidconfig()
        # Validate returned config
        if oid_config is False:
            raise Exception("Unable to fetch OpenID configuration.")
        if AUTHZ_ENDPOINT not in oid_config:
            raise Exception("Config 'authorization_endpoint' is missing.")
        if ISSUER not in oid_config:
            raise Exception("Config 'issuer' is missing.")
        auth_endpoint = oid_config.get(AUTHZ_ENDPOINT, None)
        auth_issuer = oid_config.get(ISSUER, None)

        # Send first auth request to authorization endpoint
        try:
            # Send GET and expect 302 code and location
            auth_resp = await self._request(
                url=auth_endpoint,
                headers=self.auth_headers,
                redirect=False,
                **self.auth_params,
            )
            # Validate response
            status_code = auth_resp.get(STATUS, 0)
            location = auth_resp.get(LOCATION, None)
            # Response should be 302 or 200
            if status_code not in [HTTP_REDIR, HTTP_OK]:
                raise Exception(f"Authorization of client failed: {location}")
            # Parse if there's an error in response
            if ERROR in location:
                if ERROR_DESC in location:
                    error = parse_qs(urlparse(location).query).get(ERROR_DESC, None)[0]
                else:
                    error = parse_qs(urlparse(location).query).get(ERROR, None)[0]
                raise Exception(f"Could not login: '{error}'")
        except Exception as exc:
            raise Exception("Unable to login") from exc

        # Check if we need to sign in first
        try:
            if SIGNIN_SERVICE in location:
                # Follow first redirect to get HTML data
                html_resp = await self._request(url=location, headers=self.auth_headers, redirect=False)
                if html_resp.get(STATUS, 0) is not HTTP_OK:
                    raise Exception("Failed fetching login form.")
                authz_url = await self._signin(
                    html_resp.get(DATA, None),
                    username=email,
                    password=password,
                    issuer=auth_issuer,
                    endpoint=auth_endpoint,
                )
            else:
                authz_url = location
        except Exception as exc:
            raise Exception("Signin failed") from exc

        # Expect our url at this point to be towards /oidc/v1/oauth/sso...
        if "oauth/sso" not in authz_url:
            raise Exception("Unexpected redirect, authorization failed,")

        # We are already logged on, shorter authorization flow
        try:
            authz_code = await self._authorize(authz_url)
        except Exception as exc:
            raise Exception from exc

        # Exchange authorization code for JWT tokens
        try:
            jwt_tokens = await self._exchange_code(authz_code)
            if not isinstance(jwt_tokens, dict):
                raise Exception("Token exchange failed.")
            else:
                if jwt_tokens.get(ERROR, False):
                    raise Exception(f"Exchange error: {jwt_tokens.get(ERROR)}")
            self.id_token = jwt_tokens.get(ID_TOKEN, None)
            self.access_token = jwt_tokens.get(ACCESS_TOKEN, None)
            self.refresh_token = jwt_tokens.get(REFRESH_TOKEN, None)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Exception {exc}")
        return False

    async def skoda_token(
        self: APIClient,
        code: str,
        action: str = CODE,
    ) -> dict:
        """
        Exchange authorization code for JWT tokens.
        Skoda specific Token service.
        Parameters:
            code: JWT authorization code or refresh token
            action: code, revoke or refresh
        Returns:
            dict with tokens
        """
        try:
            if action in [REVOKE, REFRESH]:
                parts = [SKODA_TOKEN, action]
                token_url = "/".join(parts)
                token_payload = {JSON: {REFRESHTOKEN: code}, PARAMS: {SYSID: self.system_id}}
            else:
                token_url = SKODA_TOKEN
                token_payload = {JSON: {AUTHZ_CODE: code}, PARAMS: {SYSID: self.system_id}}
            token_resp = await self._request(
                url=token_url,
                method=HTTP_POST,
                headers={
                    CONTENT: APP_JSON,
                },
                redirect=False,
                **token_payload,
            )
            # Validate response
            if token_resp.get(STATUS) not in [HTTP_OK, HTTP_EMPTY]:
                raise Exception("Token exchange failed.")
            # Return true if REVOKE action resulted in HTTP OK
            if action is REVOKE:
                return True
            tokens = token_resp.get(DATA)
            # Check that all tokens are received, else throw exception
            if not all(token in tokens for token in [IDTOKEN, ACCESSTOKEN, REFRESHTOKEN]):
                raise Exception("Missing token in response.")
            # Relevant checks passed, return tokens in dict
            return {
                ID_TOKEN: tokens.get(ID_TOKEN, tokens.get(IDTOKEN)),
                ACCESS_TOKEN: tokens.get(ACCESS_TOKEN, tokens.get(ACCESSTOKEN)),
                REFRESH_TOKEN: tokens.get(REFRESH_TOKEN, tokens.get(REFRESHTOKEN)),
            }
        except:  # noqa: E722
            # Return false if failed
            return False

    async def model_image(self: APIClient, vin: str, size: str = LARGE) -> Union(str, None):
        """
        Get model image url for vehicle.
        Parameters:
            vin: Vehicle vin number
            size: Type of image, small or large
        """
        try:
            # Construct message to be encrypted
            date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%mZ")
            if size not in [SMALL, LARGE]:
                raise Exception("Incorrect model image size")

            # Prepare request parameters
            req_params = {VIN: vin, VIEW: IMAGESIZE[size], DATE: date}
            parameters = urlencode(req_params, safe=":")
            # Construct message to sign
            msg = MODELAPPID + NEWLINE + MODELAPI
            sign_parts = [msg, parameters]
            to_sign = "?".join(sign_parts)

            # Construct hmac SHA-256 key object and base64 encode the message
            digest = hmac.new(MODELAPIKEY, msg=to_sign.encode(), digestmod=hashlib.sha256).digest()
            key = b64encode(digest).decode()

            # Add signing key and app id to parameters and POST data
            req_params[APPID] = MODELAPPID
            req_params[SIGN] = key
            base_url = urljoin(MODELURL, MODELAPI)
            req_url = base_url + "?" + urlencode(req_params)
            response = await self._request(
                url=req_url,
                redirect=False,
            )
            # Make sure that we got redirect and location for image
            if response.get(LOCATION, False):
                return response.get(LOCATION).split("?")[0]
        except:  # noqa: E722
            pass
        return None

    # Abstract methods, differs between children
    @abstractmethod
    async def _api_call(self: APIClient, **data) -> any:
        """Applies client specific headers etc. for API call."""

    @abstractmethod
    async def _exchange_code(self: APIClient, code: str) -> dict:
        """Exchange authorization code for JWT tokens."""

    @abstractmethod
    async def _revoke_token(self: APIClient) -> any:
        """Revoke JWT token."""

    @abstractmethod
    async def refresh_tokens(self: APIClient) -> any:
        """Refresh JWT tokens."""
