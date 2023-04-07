#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Client class with Skoda Connect services
Handles API calls and tokens.
"""

from __future__ import annotations
from jwt.exceptions import DecodeError
from aiohttp import ClientSession

from vwgconnect.platform.base import APIClient
from vwgconnect.platform.connectconst import (
    APP_URI,
    CLIENT,
    GRANTS,
    SCOPES,
    SYSTEM_ID,
    XAPPNAME,
    CUST_URL,
    MBB_STATUS,
    PERSONAL_DATA,
    CAR_DATA,
)
from vwgconnect.helper.token import decode_token
from vwgconnect.helper.html import get_nonce, get_state
from vwgconnect.string.globals import (
    CONTENT,
    APP_JSON,
    PARAMS,
    DATA,
    STATUS,
    HTTP_OK,
    NONCE,
    STATE,
    REDIR_URI,
    RES_TYPE,
    CLIENT_ID,
    SCOPE,
    SUBJECT,
    REFRESH,
    REVOKE,
    ID_TOKEN,
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    TOKENTYPE,
    HTTP_ERROR,
    HTTP_ERRORS,
    HTTP_GET,
    ERROR,
    XREQ_WITH,
    AUTHZ,
    BEARER,
)


class ConnectClient(APIClient):
    """
    'Connect' API Client used for communication with Skoda Connect.
    Used mainly for requests related to user/personal data for account.
    Used as super class for 'CABS' and 'MBB' clients.
    API customer-profile.apps.emea.vwapps.io.
    """

    def __init__(self: APIClient, http_session: ClientSession, api_debug: bool = False) -> None:
        """Initialize API Client 'Connect'."""
        super().__init__(http_session, api_debug)
        # Set Client specifics
        self.response_type = GRANTS
        self.client_id = CLIENT
        self.system_id = SYSTEM_ID
        self.scope = SCOPES
        self.redirect_uri = APP_URI
        self.app_name = XAPPNAME
        # Set payload for authz request
        self.auth_params = {
            PARAMS: {
                REDIR_URI: self.redirect_uri,
                NONCE: get_nonce(),
                STATE: get_state(),
                RES_TYPE: self.response_type,
                CLIENT_ID: self.client_id,
                SCOPE: self.scope,
            }
        }
        # Set headers to send with authz request
        self.auth_headers = {
            XREQ_WITH: self.app_name,
        }

    async def _api_call(  # pylint: disable=arguments-differ
        self: APIClient, url: str, method: str = HTTP_GET, headers: str = None, payload: any = None
    ) -> any:
        """Execute API call with common settings."""
        # Set token type for request
        sysid = "IDK_" + self.system_id
        # Set Authorization bearer
        authz_parts = [BEARER, self.access_token]
        req_headers = {CONTENT: APP_JSON, AUTHZ: " ".join(authz_parts), TOKENTYPE: sysid}
        # Update with headers specified in parameters
        if headers is not None:
            req_headers.update(headers)

        if payload is None:
            return await self._request(
                url=url,
                method=method,
                headers=req_headers,
            )
        else:
            return await self._request(url=url, method=method, headers=req_headers, **payload)

    async def _exchange_code(self: APIClient, code: str) -> dict:
        """
        Exchange authorization code for JWT tokens.
        Parameters:
            code: JWT authorization code
        Returns:
            dict with tokens
        """
        try:
            tokens = await self.skoda_token(code=code)
            return tokens
        except DecodeError:
            # Return empty dict if unable to parse received tokens
            return {ERROR: "No tokens"}

    async def _revoke_token(self: APIClient) -> bool:  # pylint: disable=arguments-differ
        """Revoke JWT (refresh) token."""
        try:
            return await self.skoda_token(
                code=self.refresh_token,
                action=REVOKE,
            )
        except DecodeError:
            return False

    async def refresh_tokens(self: APIClient) -> bool:  # pylint: disable=arguments-differ
        """Refresh JWT tokens."""
        try:
            tokens = await self.skoda_token(
                code=self.refresh_token,
                action=REFRESH,
            )
            # Validate response
            if tokens is False or isinstance(tokens, dict) is False:
                raise Exception("Token refresh failed.")
            else:
                # Revoke old refresh token
                await self._revoke_token()
                # Set new tokens
                self.id_token = tokens.get(ID_TOKEN)
                self.access_token = tokens.get(ACCESS_TOKEN)
                self.refresh_token = tokens.get(REFRESH_TOKEN)
                return True
        except DecodeError:
            return False

    # API endpoints
    async def personal_data(self: APIClient) -> dict:
        """Personal data"""
        try:
            token_claims = decode_token(self.access_token)
            subject = token_claims.get(SUBJECT, "")
            url_parts = [CUST_URL, subject, PERSONAL_DATA]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS) is not HTTP_OK:
                raise Exception(HTTP_ERRORS.get(STATUS, HTTP_ERROR))
            else:
                return response.get(DATA)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def mbb_status(self: APIClient) -> dict:
        """Get MBB status of user."""
        try:
            url_parts = [CUST_URL, self.subject, MBB_STATUS]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS) is not HTTP_OK:
                raise Exception(HTTP_ERRORS.get(STATUS, HTTP_ERROR))
            else:
                return response.get(DATA)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def car_data(self: APIClient) -> dict:
        """Get car information from profile."""
        try:
            url_parts = [CUST_URL, self.subject, CAR_DATA]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS) is not HTTP_OK:
                raise Exception(HTTP_ERRORS.get(STATUS, HTTP_ERROR))
            else:
                return response.get(DATA)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}
