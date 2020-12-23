#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vehicle class for Skoda Connect."""
import re
import time
import logging
import asyncio
import hashlib

from datetime import timedelta, datetime, timezone
from urllib.parse import urlsplit, urljoin, parse_qs, urlparse
from json import dumps as to_json
from collections import OrderedDict
import aiohttp
from bs4 import BeautifulSoup
from base64 import b64decode, b64encode
from skodaconnect.utilities import find_path, is_valid_path, read_config, json_loads

from aiohttp import ClientSession, ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST

_LOGGER = logging.getLogger(__name__)


class Vehicle:
    def __init__(self, conn, url):
        self._connection = conn
        self._url = url
        self._requests_remaining = -1
        self._request_in_progress = False
        self._request_result = 'None'
        self._climate_duration = 30

 #### API functions, parent class ####
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
            self._requests_remaining = int(req.get("rate_limit_remaining", -1))
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
            res = await self.post(query, **data)
            # Parking heater actions
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
            # VSR refresh, parking heater and lock/unlock
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
            # For electric charging, climatisation and departure timers
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
            'lock':    '/api/rolesrights/authorization/v2/vehicles/$vin/services/rlu_v1/operations/LOCK/security-pin-auth-requested',
            'unlock':  '/api/rolesrights/authorization/v2/vehicles/$vin/services/rlu_v1/operations/UNLOCK/security-pin-auth-requested',
            'heating': '/api/rolesrights/authorization/v2/vehicles/$vin/services/rheating_v1/operations/P_QSACT/security-pin-auth-requested'
            'timer':   '/api/rolesrights/authorization/v2/vehicles/$vin/services/timerprogramming_v1/operations/P_SETTINGS_AU/security-pin-auth-requested',
            'rclima':  '/api/rolesrights/authorization/v2/vehicles/$vin/services/rclima_v1/operations/P_START_CLIMA_AU/security-pin-auth-requested'
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
        from skodaconnect.dashboard import Dashboard
        return Dashboard(self, **config)

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
        """Return vehicle odometer."""
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
    def service_inspection_distance(self):
        """Return time left for service inspection"""
        return int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010003'].get('value'))

    @property
    def is_service_inspection_distance_supported(self):
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
    def oil_inspection_distance(self):
        """Return time left for service inspection"""
        return int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010001'].get('value'))

    @property
    def is_oil_inspection_distance_supported(self):
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
        """Return charger max ampere setting."""
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
                    if minutes == 65535: return "00:00"
                    return "%02d:%02d" % divmod(minutes, 60)
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
        """Return outside temperature."""
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
        if status in ['heating', 'heatingAuxiliary', 'on'] and climatisation_type == 'auxiliary':
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
        return self._climate_duration

    @pheater_duration.setter
    def pheater_duration(self, value):
        if value in [10, 20, 30, 40, 50, 60]:
            self._climate_duration = value
        else:
            _LOGGER.warning(f'Invalid value for duration: {value}')

    @property
    def is_pheater_duration_supported(self):
        return self.is_pheater_heating_supported

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
            self.requests_remaining = self.attrs.get('rate_limit_remaining')
            self.attrs.pop('rate_limit_remaining')
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

    async def lock_car(self, spin):
        if spin:
            if self.is_door_locked_supported:
                secToken = await self.requestSecToken(spin, "lock")
                url = "fs-car/bs/rlu/v1/skoda/CZ/vehicles/$vin/actions"
                data = "<rluAction xmlns=\"http://audi.de/connect/rlu\"><action>lock</action></rluAction>"
                if "Content-Type" in self._connection._session_headers:
                    contType = self._connection._session_headers["Content-Type"]
                else:
                    contType = ''

                try:
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml"
                    self._connection._session_headers["x-mbbSecToken"] = secToken
                    resp = await self.call(url, data=data)
                    if not resp:
                        _LOGGER.warning('Failed to lock car')
                    else:
                        await self.getRequestProgressStatus(resp,"rlu")
                        await self.update()
                        return
                except Exception as error:
                    _LOGGER.error('Failed to lock car - %s' % error)

                #Cleanup headers
                if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('No car lock support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def unlock_car(self, spin):
        if spin:
            if self.is_door_locked_supported:
                secToken = await self.requestSecToken(spin, "unlock")
                url = "fs-car/bs/rlu/v1/skoda/CZ/vehicles/$vin/actions"
                data = "<rluAction xmlns=\"http://audi.de/connect/rlu\"><action>unlock</action></rluAction>"
                if "Content-Type" in self._connection._session_headers:
                    contType = self._connection._session_headers["Content-Type"]
                else:
                    contType = ''

                try:
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteLockUnlock_v1_0_0+xml"
                    self._connection._session_headers["x-MbbSecToken"] = secToken
                    resp = await self.call(url, data=data)
                    if not resp:
                        _LOGGER.warning('Failed to unlock car')
                    else:
                        await self.getRequestProgressStatus(resp,"rlu")
                        await self.update()
                        return
                except Exception as error:
                    _LOGGER.error('Failed to unlock car - %s' % error)

                #Cleanup headers
                if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('No car lock support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def start_electric_climatisation(self):
        """Turn on/off climatisation."""
        if self.is_electric_climatisation_supported:
            data = {"action":{"type": "startClimatisation"}}
            try:
                resp = await self.call('fs-car/bs/climatisation/v1/Skoda/CZ/vehicles/$vin/climater/actions', json=data)
                if not resp:
                    _LOGGER.warning('Failed to start climatisation')
                else:
                    await self.getRequestProgressStatus(resp,'climatisation')
                    await self.update()
                    return resp
            except Exception as error:
                _LOGGER.warning('Failed to start climatisation - %s' % error)
        else:
            _LOGGER.error('No climatization support.')

    async def stop_electric_climatisation(self):
        """Turn on/off climatisation."""
        if self.is_electric_climatisation_supported:
            data = {"action": {"type": "stopClimatisation"}}
            resp = await self.call('fs-car/bs/climatisation/v1/Skoda/CZ/vehicles/$vin/climater/actions', json=data)
            if not resp:
                _LOGGER.warning('Failed to stop climatisation')
            else:
                await self.getRequestProgressStatus(resp,"climatisation")
                await self.update()
                return resp
        else:
            _LOGGER.error('No climatization support.')

    async def start_window_heater(self):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            data = {"action": {"type": "startWindowHeating"}}
            resp = await self.call('fs-car/bs/climatisation/v1/Skoda/CZ/vehicles/$vin/climater/actions', json=data)
            if not resp:
                _LOGGER.warning('Failed to start window heater')
            else:
                await self.getRequestProgressStatus(resp,"climatisation")
                await self.update()
                return resp
        else:
            _LOGGER.error('No window heating support.')

    async def stop_window_heater(self):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            data = {"action": {"type": "stopWindowHeating"}}
            resp = await self.call('fs-car/bs/climatisation/v1/Skoda/CZ/vehicles/$vin/climater/actions', json=data)
            if not resp:
                _LOGGER.warning('Failed to stop window heater')
            else:
                 await self.getRequestProgressStatus(resp,"climatisation")
                 await self.update()
                 return resp
        else:
            await self.update()
            _LOGGER.error('No window heating support.')

    async def start_combustion_engine_heating(self, spin, combustionengineheatingduration):
        if spin:
            if self.is_combustion_engine_heating_supported:
                secToken = await self.requestSecToken(spin, "heating")
                url = "fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action"
                data = "{ \"performAction\": { \"quickstart\": { \"climatisationDuration\": "+str(combustionengineheatingduration)+", \"startMode\": \"heating\", \"active\": true } } }"
                if "Content-Type" in self._connection._session_headers:
                    contType = self._connection._session_headers["Content-Type"]
                else:
                    contType = ''

                try:
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"
                    self._connection._session_headers["x-mbbSecToken"] = secToken
                    resp = await self.call(url, data=data)
                    if not resp:
                        _LOGGER.warning('Failed to start combustion engine heating')
                    else:
                        await self.getRequestProgressStatus(resp,"rs")
                        await self.update()
                        return
                except Exception as error:
                    _LOGGER.error('Failed to start combustion engine heating - %s' % error)

                #Cleanup headers
                if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('No combustion engine heating support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def stop_combustion_engine_heating(self):
        if self.is_combustion_engine_heating_supported or self.is_combustion_climatisation_supported:
            url = "fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action"
            data = "{ \"performAction\": { \"quickstop\": { \"active\": false } } }"
            if "Content-Type" in self._connection._session_headers:
                contType = self._connection._session_headers["Content-Type"]
            else:
                contType = ''

            try:
                self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"
                resp = await self.call(url, data=data)
                if not resp:
                    _LOGGER.warning('Failed to stop combustion engine heating')
                else:
                    await self.getRequestProgressStatus(resp,"rs")
                    await self.update()
                    return
            except Exception as error:
                _LOGGER.error('Failed to stop combustion engine heating - %s' % error)

            #Cleanup headers
            if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
            if contType: self._connection._session_headers["Content-Type"]=contType
        else:
            _LOGGER.error('No combustion engine heating support.')

    async def start_combustion_climatisation(self, spin, combustionengineclimatisationduration):
        if spin:
            if self.is_combustion_climatisation_supported:
                secToken = await self.requestSecToken(spin, "heating")
                url = "fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action"
                data = "{ \"performAction\": { \"quickstart\": { \"climatisationDuration\": "+str(combustionengineclimatisationduration)+", \"startMode\": \"ventilation\", \"active\": true } } }"
                if "Content-Type" in self._connection._session_headers:
                    contType = self._connection._session_headers["Content-Type"]
                else:
                    contType = ''

                try:
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"
                    self._connection._session_headers["x-mbbSecToken"] = secToken
                    resp = await self.call(url, data=data)
                    if not resp:
                        _LOGGER.warning('Failed to start combustion engine climatisation')
                    else:
                        await self.getRequestProgressStatus(resp,"rs")
                        await self.update()
                except Exception as error:
                    _LOGGER.error('Failed to start combustion engine climatisation - %s' % error)

                #Cleanup headers
                if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('No combustion engine climatisation support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def stop_combustion_climatisation(self):
        return await self.stop_combustion_engine_heating()

    async def start_charging(self):
        """Turn on/off charging."""
        if self.is_charging_supported:
            data = {"action": {"type": "start"}}
            resp = await self.call('fs-car/bs/batterycharge/v1/Skoda/CZ/vehicles/$vin/charger/actions', json=data)
            if not resp:
                _LOGGER.warning('Failed to start charging')
            else:
                await self.getRequestProgressStatus(resp, 'batterycharge')
                await self.update()
                return resp
        else:
            _LOGGER.error('No charging support.')

    async def stop_charging(self):
        """Turn on/off window heater."""
        if self.is_charging_supported:
            data = {"action": {"type": "stop"}}
            resp = await self.call('fs-car/bs/batterycharge/v1/Skoda/CZ/vehicles/$vin/charger/actions', json=data)
            if not resp:
                _LOGGER.warning('Failed to stop charging')
            else:
                await self.getRequestProgressStatus(resp, 'batterycharge')
                await self.update()
                return resp
        else:
            _LOGGER.error('No charging support.')

    async def set_climatisation_target_temperature(self, target_temperature):
        """Turn on/off window heater."""
        if self.is_electric_climatisation_supported:
        #or self.is_combustion_climatisation_supported:
            resp = await self.call('-/emanager/set-settings', chargerMaxCurrent=None, climatisationWithoutHVPower=None, minChargeLimit=None, targetTemperature=target_temperature)
            if not resp:
                _LOGGER.warning('Failed to set target temperature for climatisation')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No climatisation support.')

    async def get_status(self, timeout=10):
        """Check status from call"""
        retry_counter = 0
        while retry_counter < timeout:
            resp = await self.call('-/emanager/get-notifications', data='dummy')
            data = resp.get('actionNotificationList', {})
            if data:
                return data
            time.sleep(1)
            retry_counter += 1
        return False

    def __str__(self):
        return self.vin

    @property
    def json(self):
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
        return to_json(
            OrderedDict(sorted(self.attrs.items())),
            indent=4,
            default=serialize
        )
