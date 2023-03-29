#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Client class for Skoda Connect services
Handles API calls and tokens.
"""

from __future__ import annotations
from aiohttp import ClientSession
from vwgconnect.platform.base import APIClient
from vwgconnect.string.globals import (
    PARAMS,
    IDENTITIES,
    SETTINGS,
    TIMERS,
    PARK_POS,
    MODE,
    NONCE,
    STATE,
    REDIR_URI,
    RES_TYPE,
    CLIENT_ID,
    SCOPE,
    REFRESH,
    REVOKE,
    SUBJECT,
    ID_TOKEN,
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    TOKENTYPE,
    ERROR,
    STATUS,
    DATA,
    HTTP_OK,
    HTTP_GET,
    HTTP_POST,
    XREQ_WITH,
    BEARER,
    CONTENT,
    APP_JSON,
    AUTHZ,
    V1,
    V3,
    VIN,
    TYPE,
)
from .skodaconst import (
    APP_URI,
    CLIENT,
    GRANTS,
    SCOPES,
    SYSTEM_ID,
    XAPPNAME,
    OPREQS,
    BASE_URL,
    VEHICLES,
    GARAGE,
    USERS,
    CHARGING,
    AIRCON,
    CAR_STATUS,
    POSITION,
    START,
    STOP,
    UPDATE,
    CHARGECONFIG,
    CHARGEAMPERE,
    CHARGEUNLOCK,
    CHARGETARGET,
)
from vwgconnect.helper.token import decode_token
from vwgconnect.helper.html import get_nonce, get_state


class TechnicalClient(APIClient):
    """
    'Technical' API Client used for communication with Skoda Connect.
    Used mainly for requests to Skoda hosted API.
    API base domain:
        api.connect.skoda-auto.cz.
    """

    def __init__(self: APIClient, http_session: ClientSession, api_debug: bool = False) -> None:
        """Initialize API Client 'Technical'."""
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
        except:  # pylint: disable=broad-except, bare-except
            # Return empty dict if unable to parse received tokens
            return {ERROR: "No tokens"}

    async def _revoke_token(self: APIClient) -> bool:  # pylint: disable=arguments-differ
        """Revoke JWT (refresh) token."""
        try:
            return await self.skoda_token(
                code=self.refresh_token,
                action=REVOKE,
            )
        except:  # pylint: disable=broad-except, bare-except
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
        except:  # pylint: disable=bare-except
            return False

    async def request_status(  # pylint: disable=arguments-differ
        self: APIClient, vin: str, section: str, req_id: int
    ) -> str:
        """
        Fetch status of ongoing request.
        Parameters:
            vin: Vehicle vin number
            function: The 'endpoint'
            req_id: Request ID
        Returns status text string
        """

    # API endpoints
    # Methods for fetching user data
    async def identities(self: APIClient) -> dict:
        """Return user identity information"""
        try:
            # Get user id from subject claim in JWT token
            token_claims = decode_token(self.access_token)
            subject = token_claims.get(SUBJECT, "")
            # Construct URL with user id between the other URL parts
            url_parts = [BASE_URL, V1, USERS, subject, IDENTITIES]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def garage(self: APIClient) -> dict:
        """Return garage information"""
        try:
            url_parts = [BASE_URL, V3, GARAGE]
            response = await self._api_call("/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    # Methods for fetching vehicle data
    async def vehicle(self: APIClient, vin: str) -> dict:
        """
        Return vehicle information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: Vehicle information
        """
        try:
            url_parts = [BASE_URL, V3, GARAGE, VEHICLES, vin]
            req_url = "/".join(url_parts)
            response = await self._request(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
            elif response.get(ERROR, False):
                return response
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def position(self: APIClient, vin: str) -> dict:
        """
        Return vehicle position information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: Parking position data
        """
        try:
            url_parts = [BASE_URL, V1, POSITION, VEHICLES, vin, PARK_POS]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def status(self: APIClient, vin: str) -> dict:
        """
        Return vehicle status information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: status data
        """
        try:
            url_parts = [BASE_URL, V1, CAR_STATUS, vin]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _get_charging(self: APIClient, idx: str, typ: str = STATUS) -> dict:
        """
        Return charging status information.
        Parameters:
            idx: identifier, Vehicle VIN or request id
            typ: endpoint type, default STATUS
        Returns:
            dict: charging data
        """
        try:
            if typ not in [MODE, STATUS, SETTINGS, OPREQS]:
                raise Exception("Invalid type.")
            # Build URL for API request
            if idx is OPREQS:
                url_parts = [BASE_URL, V1, CHARGING, typ, idx]
            else:
                url_parts = [BASE_URL, V1, CHARGING, idx, typ]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_mode(self: APIClient, vin: str) -> dict:
        """
        Return charging mode information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: charging mode
        """
        try:
            return await self._get_charging(vin, MODE)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_status(self: APIClient, vin: str) -> dict:
        """
        Return charging status information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: charging status
        """
        try:
            return await self._get_charging(vin, STATUS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_settings(self: APIClient, vin: str) -> dict:
        """
        Return charging settings information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: charging settings
        """
        try:
            return await self._get_charging(vin, SETTINGS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_request(self: APIClient, req_id: str) -> dict:
        """
        Return status of operation request information.
        Parameters:
            req_id: Request ID
        Returns:
            dict: charging settings
        """
        try:
            return await self._get_charging(req_id, OPREQS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _get_aircon(self: APIClient, idx: str, typ: str = STATUS) -> dict:
        """
        Return air-conditioning information.
        Parameters:
            idx: Vehicle VIN number
            typ: Type of information, default STATUS
        Returns:
            dict: charging data
        """
        try:
            if typ not in [STATUS, SETTINGS, TIMERS, OPREQS]:
                raise Exception("Invalid type.")
            if idx is OPREQS:
                url_parts = [BASE_URL, V1, AIRCON, typ, idx]
            else:
                url_parts = [BASE_URL, V1, AIRCON, idx, typ]
            req_url = "/".join(url_parts)
            response = await self._api_call(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aircon_status(self: APIClient, vin: str) -> dict:
        """
        Return air-conditioning status information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: air-conditioning status
        """
        try:
            return await self._get_aircon(vin, STATUS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aircon_settings(self: APIClient, vin: str) -> dict:
        """
        Return air-conditioning settings information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: air-conditioning settings
        """
        try:
            return await self._get_aircon(vin, SETTINGS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aircon_timers(self: APIClient, vin: str) -> dict:
        """
        Return air-conditioning timers information.
        Parameters:
            vin: Vehicle VIN number
        Returns:
            dict: air-conditioning timers
        """
        try:
            return await self._get_aircon(vin, TIMERS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aircon_request(self: APIClient, req_id: str) -> dict:
        """
        Return status of operation request information.
        Parameters:
            req_id: Request ID
        Returns:
            dict: air-conditioning operation request status
        """
        try:
            return await self._get_aircon(req_id, OPREQS)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    # Methods for setting vehicle data
    async def _set(self: APIClient, url: str, payload: dict, headers: dict = None) -> dict:
        """
        Method to POST settings to API.
        Parameters:
            url: url to POST to
            headers: dict with additional HTTP headers
            payload: Json/Parameters/Data to POST
        """
        try:
            response = await self._api_call(url=url, method=HTTP_POST, headers=headers, **payload)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_charger(
        self: APIClient,
        payload: dict,
        headers: dict = None,
    ) -> str:
        """
        Method to set vehicle charger settings.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
        """
        try:
            url_parts = [BASE_URL, V1, CHARGING, OPREQS]
            return await self._set(
                url="/".join(url_parts),
                payload=payload,
                headers=headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_start(
        self: APIClient,
        vin: str,
    ) -> str:
        """
        Method to start charging car.
        Parameters:
            vin: Vehicle VIN number
        """
        try:
            req_payload = {DATA: {TYPE: START.capitalize()}, PARAMS: {VIN: vin}}
            return await self._set_charger(payload=req_payload)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_stop(
        self: APIClient,
        vin: str,
    ) -> str:
        """
        Method to stop charging car.
        Parameters:
            vin: Vehicle VIN number
        """
        try:
            req_payload = {DATA: {TYPE: STOP.capitalize()}, PARAMS: {VIN: vin}}
            return await self._set_charger(payload=req_payload)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_config(self: APIClient, vin: str, data: dict) -> str:
        """
        Method to stop charging car.
        Parameters:
            vin: Vehicle VIN number
            data: the 'chargingSettings' dict
        Returns:
            dict with request result
        """
        try:
            # Validate settings
            if not CHARGECONFIG in data:
                raise Exception("Missing settings for set request")
            else:
                if not all(
                    setting in data[CHARGECONFIG]
                    for setting in [CHARGEAMPERE, CHARGETARGET, CHARGEUNLOCK]
                ):
                    raise Exception("Missing settings for set request")
            req_payload = {DATA: {**data, TYPE: UPDATE}, PARAMS: {VIN: vin}}
            return await self._set_charger(payload=req_payload)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}
