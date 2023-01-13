#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Client class with Skoda Connect services
Handles API calls and tokens.
"""

from __future__ import annotations
#from typing import Union, Optional
from aiohttp import ClientSession
from skodaconnect.api.base.base import APIClient
from skodaconnect.api.base.const import (
    REQ_PARAMS,
    STATUS,
    SYSID,
    ERROR,
    DATA,
)
from skodaconnect.api.connect.const import (
    APP_URI, CLIENT, GRANTS, SCOPES, SYSTEM_ID, XAPPNAME,
    IDTOKEN, ACCESSTOKEN, REFRESHTOKEN
)
from skodaconnect.helpers.html import get_nonce, get_state
from skodaconnect.strings.jwt import * # pylint: disable=unused-wildcard-import, wildcard-import
from skodaconnect.strings.urls import * # pylint: disable=unused-wildcard-import, wildcard-import
from skodaconnect.strings.http import (
    CONTENT,
    APP_JSON,
    HTTP_OK,
    HTTP_POST,
    #HTTP_GET,
    #HTTP_OTHER,
    #HTTP_REDIR,
    #HTTP_MOVED,
    XREQ_WITH
)

class ConnectClient(APIClient):
    """
    'Connect' API Client used for communication with Skoda Connect.
    Used mainly for requests related to user/personal data for account.
    Also used for fetching 'CABS' token.
    API customer-profile.apps.emea.vwapps.io.
    """

    def __init__(
        self: APIClient,
        http_session: ClientSession,
        api_debug: bool = False
    ) -> None:
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
            REQ_PARAMS: {
                REDIR_URI: self.redirect_uri,
                NONCE: get_nonce(),
                STATE: get_state(),
                RES_TYPE: self.response_type,
                CLIENT_ID: self.client_id,
                SCOPE: self.scope
            }
        }
        # Set headers to send with authz request
        self.auth_headers = {
            XREQ_WITH: self.app_name,
        }

    async def _exchange_code(self: APIClient, code: str) -> dict:
        """
        Exchange authorization code for JWT tokens.
        Parameters:
            code: JWT authorization code
        Returns:
            dict with tokens
        """
        try:
            token_resp = await self._request(
                url = TOKEN_URL,
                method = HTTP_POST,
                headers = {
                    CONTENT: APP_JSON,
                },
                json = {
                    AUTHZ_CODE: code
                },
                params = {
                    SYSID: self.system_id
                },
                redirect = False
            )
            tokens = token_resp.get(DATA, {})
            # Validate response
            if token_resp.get(STATUS) is not HTTP_OK:
                raise Exception("Token exchange failed.")
            if token_resp.get(ERROR, False):
                raise Exception(token_resp.get(ERROR))
            if not all(token in tokens for token in [
                IDTOKEN, ACCESSTOKEN, REFRESHTOKEN
            ]):
                raise Exception("Missing token in response.")
        except Exception as exc:
            raise Exception from exc

        try:
            print(f"Return with {tokens}")
            return {
                ID_TOKEN: tokens.get(ID_TOKEN, tokens.get(IDTOKEN)),
                ACCESS_TOKEN: tokens.get(ACCESS_TOKEN, tokens.get(ACCESSTOKEN)),
                REFRESH_TOKEN: tokens.get(REFRESH_TOKEN, tokens.get(REFRESHTOKEN))
            }
        except:  # pylint: disable=broad-except, bare-except
            # Return empty dict if unable to parse received tokens
            return {}

    async def get_tokens(self: APIClient, code: str) -> dict: # pylint: disable=arguments-differ
        """
        Exchange authorization code for JWT tokens.
        Parameters:
            code: authorization code
        Returns:
            dictionary with tokens.
        """

    async def refresh_tokens(self: APIClient) -> bool: # pylint: disable=arguments-differ
        """Refresh JWT tokens."""

    async def revoke_token(self: APIClient, token: str) -> bool: # pylint: disable=arguments-differ
        """Revoke a JWT (refresh) token."""

    async def request_status( # pylint: disable=arguments-differ
        self:       APIClient,
        vin:        str,
        section:    str,
        req_id:     int
    ) -> str:
        """
        Fetch status of ongoing request.
        Parameters:
            vin: Vehicle vin number
            function: The 'endpoint'
            req_id: Request ID
        Returns status text string
        """
