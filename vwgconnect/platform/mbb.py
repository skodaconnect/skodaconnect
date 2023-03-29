#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Client class for Skoda Connect services
Handles API calls and tokens.
"""

from __future__ import annotations
from typing import Union
from aiohttp import ClientSession
from vwgconnect.platform.connect import ConnectClient
from vwgconnect.helper.token import token_valid
from vwgconnect.platform.mbbconst import (
    SCOPES,
    XCLIENT,
    MBBOAUTH2,
    GARAGE_URL,
    HOME_URL,
    BASE_URL,
    OPER_LIST,
    TRIP_URL,
    POS_URL,
    STATUS_URL,
    TIMER_URL,
    CLIMATE_URL,
    CHARGE_URL,
    AUX_URL,
    HNF_URL,
    LOCK_URL,
    BRAND,
    COUNTRY,
    SHORTTERM,
    LONGTERM,
    CYCLIC,
    NEWEST,
    LIST,
    XNAME,
    XVERSION,
    REQUESTS,
    JOBSTATUS,
    APP_LOCKXML,
    APP_RSJSON,
    SETSETTINGS,
    MAXCURRENT,
)
from vwgconnect.string.globals import (
    DATA,
    TOKEN,
    GRANT_TYPE,
    SCOPE,
    ACTIONS,
    HTTP_GET,
    HTTP_POST,
    HTTP_OK,
    HTTP_THROTTLED,
    HTTP_ERRORS,
    STATUS,
    ERROR,
    ACTION,
    ID_TOKEN,
    ACCESS_TOKEN,
    REFRESH_TOKEN,
    XCLIENT_ID,
    REVOKE,
    V1,
    TOKENHINT,
    BEARER,
    ACCEPT,
    APP_JSON,
    CONTENT,
    AUTHZ,
    XAPP_NAME,
    XAPP_VER,
    TYPE,
    SETTINGS,
    START,
    STOP,
)


class MBBClient(ConnectClient):
    """
    'MBB' API Client used for communication with Skoda Connect.
    Used mainly for requests towards VW-Group API for vehicle data.
    Requires 'Connect' instance, its id_token is used for authorization.
    API base domains:
        vwg-connect.com
        volkswagen.de
    """

    def __init__(self: ConnectClient, http_session: ClientSession, api_debug: bool = False) -> None:
        """
        Initialize API Client 'MBB'.
        Parameters:
            http_session: aiohttp ClientSession,
            id_token: 'Connect' client id_token
            api_debug: Enable API debugging
        """
        super().__init__(http_session, api_debug)
        # Set Client specifics
        self._mbb_tokens = {}

    # Properties of class instance, no id token for MBB client
    @property
    def mbb_access_token(self: ConnectClient) -> Union(str, None):
        """Return MBB Access Token."""
        try:
            return self._mbb_tokens.get(ACCESS_TOKEN, None)
        except:  # pylint: disable=bare-except
            return None

    @mbb_access_token.setter
    def mbb_access_token(self: ConnectClient, token: str) -> None:
        """
        Set MBB Access token.
        Parameters:
            token: token string
        """
        if not token_valid(token):
            raise Exception("Invalid access token")
        if isinstance(token, str):
            self._mbb_tokens[ACCESS_TOKEN] = token

    @property
    def mbb_refresh_token(self: ConnectClient) -> Union(str, None):
        """Return Refresh Token."""
        try:
            return self._mbb_tokens.get(REFRESH_TOKEN, None)
        except:  # pylint: disable=bare-except
            return None

    @mbb_refresh_token.setter
    def mbb_refresh_token(self: ConnectClient, token: str) -> None:
        """
        Set Refresh token.
        Parameters:
            token: token string
        """
        if not token_valid(token):
            raise Exception("Invalid refresh token")
        if isinstance(token, str):
            self._mbb_tokens[REFRESH_TOKEN] = token

    async def _mbb_api_call(  # pylint: disable=arguments-differ
        self: ConnectClient,
        url: str,
        method: str = HTTP_GET,
        headers: str = None,
        payload: any = None,
    ) -> any:
        """
        Applies client specific headers and executes API call.
        Parameters:
            url: URL to GET/POST to
            method: GET or POST, defaults to GET
            headers: HTTP headers to add to request, optional
            payload: data/parameters for POST
        Returns:
            dict: API json data in dictionary form
        """
        # Set client specific headers for API calls
        authz_parts = [BEARER, self.mbb_access_token]
        req_headers = {
            ACCEPT: APP_JSON,
            CONTENT: APP_JSON,
            AUTHZ: " ".join(authz_parts),
            XAPP_NAME: XNAME,
            XAPP_VER: XVERSION,
        }
        # Merge with headers specified in parameters
        if headers is not None:
            req_headers.update(headers)
        # Send HTTP GET if no payload is specified
        if payload is None:
            req_headers.pop(CONTENT, None)
            return await self._request(
                url=url,
                method=method,
                headers=req_headers,
            )
        else:
            return await self._request(url=url, method=method, headers=req_headers, **payload)

    async def get_mbb_tokens(self: ConnectClient) -> bool:
        """
        Use Connect (parent) id token to fetch MBB API tokens.
        Returns:
            True if succeeded
            False if failed
        """
        try:
            url_parts = [MBBOAUTH2, V1, TOKEN]
            token_url = "/".join(url_parts)
            token_resp = await self._request(
                url=token_url,
                method=HTTP_POST,
                headers={XCLIENT_ID: XCLIENT},
                data={TOKEN: self.id_token, GRANT_TYPE: ID_TOKEN, SCOPE: SCOPES},
                redirect=False,
            )
            if token_resp.get(STATUS) is HTTP_OK:
                tokens = token_resp.get(DATA, {})
                self.mbb_access_token = tokens.get(ACCESS_TOKEN, None)
                self.mbb_refresh_token = tokens.get(REFRESH_TOKEN, None)
                return True
        except:  # pylint: disable=bare-except
            pass
        return False

    async def revoke_mbb_token(self: ConnectClient, typ: str = ACCESS_TOKEN) -> bool:
        """
        Revoke MBB JWT token
        Parameters:
            typ: which token to revoke; access_token or refresh_token
        Returns:
            True if succeeded
            False if failed
        """
        try:
            if typ not in [ACCESS_TOKEN, REFRESH_TOKEN]:
                raise Exception("Invalid token type for revoke.")
            url_parts = [MBBOAUTH2, V1, REVOKE]
            revoke_url = "/".join(url_parts)
            if typ is ACCESS_TOKEN:
                token = self.mbb_access_token
            else:
                token = self.mbb_refresh_token
            revoke_resp = await self._request(url=revoke_url, data={TOKEN: token, TOKENHINT: typ})
            if revoke_resp.get(STATUS, 0) == HTTP_OK:
                return True
        except:  # pylint: disable=bare-except
            pass
        return False

    async def refresh_tokens(self: ConnectClient) -> bool:  # pylint: disable=arguments-differ
        """Refresh JWT tokens."""
        try:
            # Refresh parent Connect tokens if expired
            if not token_valid(self.id_token):
                await super().refresh_tokens()
            # Try to refresh tokens first, will fail if new Connect tokens
            url_parts = [MBBOAUTH2, V1, TOKEN]
            token_url = "/".join(url_parts)
            token_resp = await self._request(
                url=token_url,
                data={TOKEN: self.mbb_refresh_token, GRANT_TYPE: REFRESH_TOKEN, SCOPE: SCOPES},
            )
            if token_resp.get(STATUS) is HTTP_OK:
                tokens = token_resp.get(DATA, {})
                self.revoke_mbb_token(ACCESS_TOKEN)
                self.mbb_access_token = tokens.get(ACCESS_TOKEN, None)
                self.revoke_mbb_token(REFRESH_TOKEN)
                self.mbb_refresh_token = tokens.get(REFRESH_TOKEN, None)
                return True
            else:
                # Connect id_token might have changed, fetch new MBB tokens
                return await self.get_mbb_tokens()
        except:  # pylint: disable=bare-except
            return False

    async def auth(self: ConnectClient, email: str, password: str) -> bool:
        """Login/authorize client."""
        print("Authorizing super class...")
        await super().auth(email, password)
        # Check ID token and get MBB API Tokens
        if self.id_token is None:
            return False
        else:
            return await self.get_mbb_tokens()

    # Methods for fetching user data
    async def garage(self: ConnectClient) -> dict:
        """Return garage information"""
        try:
            response = await self._mbb_api_call(GARAGE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    # Methods for fetching vehicle data
    async def home_region(self: ConnectClient, vin: str) -> dict:
        """Return home region, API base URL, for vehicle."""
        try:
            req_url = HOME_URL.format(VIN=vin)
            response = await self._mbb_api_call(req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def operation_list(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Get operationlist for VIN, supported/licensed functions."""
        try:
            endpoint = OPER_LIST.format(VIN=vin)
            url_parts = [base, endpoint]
            response = await self._mbb_api_call("/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def position(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Return dict with vehicle status."""
        try:
            endpoint = POS_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def status(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Return dict with vehicle status."""
        try:
            endpoint = STATUS_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, STATUS]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def status_request(
        self: ConnectClient, vin: str, reqid: str, base: str = BASE_URL
    ) -> dict:
        """
        Return information about vehicle status refresh request.
        Parameters:
            vin: Vehicle VIN number
            reqid: request ID
            base: home region of vehicle
        """
        try:
            endpoint = STATUS_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, REQUESTS, reqid, JOBSTATUS]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def trip_stats(
        self: ConnectClient,
        vin: str,
        base: str = BASE_URL,
        period: str = SHORTTERM,
        typ: str = NEWEST,
    ) -> dict:
        """Return dict with vehicle status."""
        try:
            if typ not in [NEWEST, LIST]:
                raise Exception("Invalid type for trip statistics")
            if period not in [SHORTTERM, LONGTERM, CYCLIC]:
                raise Exception("Invalid period for trip statistics")
            endpoint = TRIP_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, period]
            req_url = "/".join(url_parts) + "?" + typ
            response = await self._mbb_api_call(url=req_url)
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def timers(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Return dict with vehicle departure timer settings."""
        try:
            endpoint = TIMER_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def timer_request(
        self: ConnectClient, vin: str, reqid: str, base: str = BASE_URL
    ) -> dict:
        """
        Return information about dparture timer operation request.
        Parameters:
            vin: Vehicle VIN number
            reqid: request ID
            base: home region of vehicle
        """
        try:
            endpoint = TIMER_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, ACTIONS, reqid]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aircon_status(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Return dict with vehicle departure timer settings."""
        try:
            endpoint = CLIMATE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aircon_request(
        self: ConnectClient, vin: str, reqid: str, base: str = BASE_URL
    ) -> dict:
        """
        Return information about climatisation operation request.
        Parameters:
            vin: Vehicle VIN number
            reqid: request ID
            base: home region of vehicle
        """
        try:
            endpoint = CLIMATE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, ACTIONS, reqid]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_status(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Return dict with vehicle departure timer settings."""
        try:
            endpoint = CHARGE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charging_request(
        self: ConnectClient, vin: str, reqid: str, base: str = BASE_URL
    ) -> dict:
        """
        Return information about charging operation request.
        Parameters:
            vin: Vehicle VIN number
            reqid: request ID
            base: home region of vehicle
        """
        try:
            endpoint = CHARGE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, ACTIONS, reqid]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aux_heater(self: ConnectClient, vin: str, base: str = BASE_URL) -> dict:
        """Return dict with vehicle departure timer settings."""
        try:
            endpoint = AUX_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, STATUS]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def aux_heater_request(
        self: ConnectClient, vin: str, reqid: str, base: str = BASE_URL
    ) -> dict:
        """
        Return information about charging operation request.
        Parameters:
            vin: Vehicle VIN number
            reqid: request ID
            base: home region of vehicle
        """
        try:
            endpoint = AUX_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, REQUESTS, reqid, STATUS]
            response = await self._mbb_api_call(url="/".join(url_parts))
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    # Methods for setting vehicle data
    async def _mbb_set(self: ConnectClient, url: str, payload: dict, headers: dict = None) -> dict:
        """
        Method to POST settings to 'MBB' API.
        Parameters:
            url: url to POST to
            headers: dict with additional HTTP headers
            payload: Json/Parameters/Data to POST
        """
        try:
            response = await self._mbb_api_call(
                url=url, method=HTTP_POST, headers=headers, **payload
            )
            if response.get(STATUS, 0) is HTTP_OK:
                return response.get(DATA, {})
            elif response.get(STATUS, 0) is HTTP_THROTTLED:
                return {ERROR: HTTP_ERRORS[HTTP_THROTTLED]}
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_charger(
        self: ConnectClient, vin: str, payload: dict, headers: dict = None, base: str = BASE_URL
    ) -> str:
        """
        Method to set vehicle charger settings.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
            base: Vehicle home region URL
        """
        try:
            endpoint = CHARGE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, ACTIONS]
            return await self._mbb_set(
                url="/".join(url_parts),
                payload=payload,
                headers=headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_aircon(
        self: ConnectClient, vin: str, payload: dict, headers: dict = None, base: str = BASE_URL
    ) -> str:
        """
        Method to set vehicle charger settings.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
            base: Vehicle home region URL
        """
        try:
            endpoint = CLIMATE_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, ACTIONS]
            return await self._mbb_set(
                url="/".join(url_parts),
                payload=payload,
                headers=headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_timer(
        self: ConnectClient, vin: str, payload: dict, headers: dict = None, base: str = BASE_URL
    ) -> str:
        """
        Method to set vehicle departure schedule settings.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
            base: Vehicle home region URL
        """
        try:
            endpoint = TIMER_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint, ACTIONS]
            return await self._mbb_set(
                url="/".join(url_parts),
                payload=payload,
                headers=headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_honkandflash(
        self: ConnectClient, vin: str, payload: dict, headers: dict = None, base: str = BASE_URL
    ) -> str:
        """
        Method to activate vehicle honk and/or flash.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
            base: Vehicle home region URL
        """
        try:
            endpoint = HNF_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            url_parts = [base, endpoint]
            return await self._mbb_set(
                url="/".join(url_parts),
                payload=payload,
                headers=headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_lock(
        self: ConnectClient, vin: str, payload: dict, headers: dict = None, base: str = BASE_URL
    ) -> str:
        """
        Method to lock or unlock vehicle.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
            base: Vehicle home region URL
        """
        try:
            endpoint = LOCK_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            req_headers = headers
            extra_header = {CONTENT: APP_LOCKXML}
            req_headers.update(extra_header)
            url_parts = [base, endpoint, ACTIONS]
            return await self._mbb_set(
                url="/".join(url_parts),
                payload=payload,
                headers=req_headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def _set_aux_heater(
        self: ConnectClient, vin: str, payload: dict, headers: dict = None, base: str = BASE_URL
    ) -> str:
        """
        Method to start/stop parking heater.
        Parameters:
            vin: Vehicle VIN number
            payload: Json/Parameters/Data to POST
            headers: Extra headers
            base: Vehicle home region URL
        """
        try:
            endpoint = LOCK_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            req_headers = headers
            extra_header = {CONTENT: APP_RSJSON}
            req_headers.update(extra_header)
            url_parts = [base, endpoint, ACTIONS]
            return await self._mbb_set(
                url="/".join(url_parts),
                payload=payload,
                headers=req_headers,
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    # Vehicle operation methods
    async def vehicle_refresh(self: ConnectClient, vin: str, base: str = BASE_URL) -> str:
        """
        Method to request data refresh from car.
        Parameters:
            vin: Vehicle VIN number
            base: Vehicle home region URL
        """
        try:
            endpoint = LOCK_URL.format(BRAND=BRAND, COUNTRY=COUNTRY, VIN=vin)
            req_payload = {DATA: None}
            url_parts = [base, endpoint, REQUESTS]
            return await self._mbb_set(url="/".join(url_parts), payload=req_payload)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def start_charging(self: ConnectClient, vin: str, base: str = BASE_URL) -> str:
        """
        Method to start charging car.
        Parameters:
            vin: Vehicle VIN number
            base: Vehicle home region URL
        """
        try:
            req_payload = {DATA: {ACTION: {TYPE: START}}}
            return await self._set_charger(vin=vin, payload=req_payload, base=base)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def stop_charging(self: ConnectClient, vin: str, base: str = BASE_URL) -> str:
        """
        Method to stop charging car.
        Parameters:
            vin: Vehicle VIN number
            base: Vehicle home region URL
        """
        try:
            req_payload = {DATA: {ACTION: {TYPE: STOP}}}
            return await self._set_charger(vin=vin, payload=req_payload, base=base)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}

    async def charge_current(
        self: ConnectClient, vin: str, value: int, base: str = BASE_URL
    ) -> str:
        """
        Method to set charger maximum current.
        Parameters:
            vin: Vehicle VIN number
            value: Charge current (1-254)
                    252 = Reduced
                    254 = Maximum
            base: Vehicle home region URL
        """
        try:
            if int(value) not in range(1, 254):
                raise Exception("Invalid value for charger current")
            req_payload = {DATA: {ACTION: {SETTINGS: {MAXCURRENT: int(value)}, TYPE: SETSETTINGS}}}
            return await self._set_charger(vin=vin, payload=req_payload, base=base)
        except Exception as exc:  # pylint: disable=broad-except
            return {ERROR: exc}
