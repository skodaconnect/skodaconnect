#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vehicle class for Skoda Connect."""
import re
import time
import logging
import asyncio
import hashlib

from datetime import datetime, timedelta, timezone
from json import dumps as to_json
from collections import OrderedDict
from skodaconnect.utilities import find_path, is_valid_path

_LOGGER = logging.getLogger(__name__)


class Vehicle:
    def __init__(self, conn, data):
        _LOGGER.debug(f'Creating Vehicle class object with data {data}')
        self._connection = conn
        #self._url = url
        self._url = data.get('vin', '')
        self._service = data.get('service', '')
        self._capabilities = data.get('capabilities', '')
        self._homeregion = 'https://msg.volkswagen.de'
        self._discovered = False
        self._states = {}
        self._requests = {
            #'departuretimer': {'status': '', 'timestamp': datetime.now()}, # Not yet implemented
            'batterycharge': {'status': '', 'timestamp': datetime.now()},
            'climatisation': {'status': '', 'timestamp': datetime.now()},
            'refresh': {'status': '', 'timestamp': datetime.now()},
            'lock': {'status': '', 'timestamp': datetime.now()},
            'preheater': {'status': '', 'timestamp': datetime.now()},
            'remaining': -1,
            'latest': '',
            'state': ''
        }
        self._climate_duration = 30

        # API Endpoints that might be enabled for car (that we support)
        if self._service == 'ONLINE':
            self._services = {
                'rheating_v1': {'active': False},
                'rclima_v1': {'active': False},
                'rlu_v1': {'active': False},
                'trip_statistic_v1': {'active': False},
                'statusreport_v1': {'active': False},
                'rbatterycharge_v1': {'active': False},
                'rhonk_v1': {'active': False},
                'carfinder_v1': {'active': False},
                #'timerprogramming_v1': {'active': False}, # Not yet implemented
            }
        elif self._service == 'REMOTE':
            self._services = {
                'CHARGING': {'active': False}
            }

 #### API get and set functions ####
  # Init and update vehicle data
    async def discover(self):
        """Discover vehicle and initial data."""
        # For VW-Group API
        if self._service == 'ONLINE':
            _LOGGER.debug(f'Starting discovery for vehicle {self.vin}')
            homeregion = await self._connection.getHomeRegion(self.vin)
            _LOGGER.debug(f'Get homeregion for VIN {self.vin}')
            if homeregion:
                self._homeregion = homeregion

            await asyncio.gather(
                self.get_carportdata(),
                self.get_realcardata(),
                return_exceptions=True
            )
            _LOGGER.info(f'Vehicle {self.vin} added. Homeregion is "{self._homeregion}"')

            _LOGGER.debug('Attempting discovery of supported API endpoints for vehicle.')
            operationList = await self._connection.getOperationList(self.vin)
            if operationList:
                serviceInfo = operationList['serviceInfo']
                # Iterate over all endpoints in ServiceInfo list
                for service in serviceInfo:
                    try:
                        if service.get('serviceId', 'Invalid') in self._services.keys():
                            data = {}
                            serviceName = service.get('serviceId', None)
                            if service.get('serviceStatus', {}).get('status', 'Disabled') == 'Enabled':
                                _LOGGER.debug(f'Discovered enabled service: {service["serviceId"]}')
                                data['active'] = True
                                if service.get('cumulatedLicense', {}).get('expirationDate', False):
                                    data['expiration'] = service.get('cumulatedLicense', {}).get('expirationDate', None).get('content', None)
                                if service.get('operation', False):
                                    data.update({'operations': []})
                                    for operation in service.get('operation', []):
                                        data['operations'].append(operation.get('id', None))
                            elif service.get('serviceStatus', {}).get('status', None) == 'Disabled':
                                reason = service.get('serviceStatus', {}).get('reason', 'Unknown')
                                _LOGGER.debug(f'Service: {serviceName} is disabled because of reason: {reason}')
                                data['active'] = False
                            else:
                                _LOGGER.warning(f'Could not determine status of service: {serviceName}, assuming enabled')
                                data['active'] = True
                            self._services[serviceName].update(data)
                    except Exception as error:
                        _LOGGER.warning(f'Encountered exception: "{error}" while parsing service item: {service}')
                        pass
            else:
                _LOGGER.warning(f'Could not determine available API endpoints for {self.vin}')
        # For Skoda native API:
        else:
            for service in self._services:
                for capability in self._capabilities:
                    if capability == service:
                        self._services[service]['active'] = True

        _LOGGER.debug(f'API endpoints: {self._services}')
        self._discovered = True

    async def update(self):
        """Try to fetch data for all known API endpoints."""
        if not self._discovered:
            await self.discover()
        if not self.deactivated:
            await asyncio.gather(
                self.get_preheater(),
                self.get_climater(),
                self.get_trip_statistic(),
                self.get_position(),
                self.get_statusreport(),
                self.get_charger(),
                self.get_timerprogramming(),
                return_exceptions=True
            )
        else:
            _LOGGER.info(f'Vehicle with VIN {self.vin} is deactivated.')

  # Data collection functions
    async def get_realcardata(self):
        """Fetch realcar data."""
        data = await self._connection.getRealCarData(self.vin)
        if data:
            self._states.update(data)

    async def get_carportdata(self):
        """Fetch carport data."""
        data = await self._connection.getCarportData(self.vin)
        if data:
            self._states.update(data)

    async def get_preheater(self):
        """Fetch pre-heater data if function is enabled."""
        if self._services.get('rheating_v1', {}).get('active', False):
            if not await self.expired('rheating_v1'):
                data = await self._connection.getPreHeater(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch preheater data')
        else:
            self._requests.pop('preheater', None)

    async def get_climater(self):
        """Fetch climater data if function is enabled."""
        if self._services.get('rclima_v1', {}).get('active', False):
            if not await self.expired('rclima_v1'):
                data = await self._connection.getClimater(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch climater data')
        else:
            self._requests.pop('climatisation', None)

    async def get_trip_statistic(self):
        """Fetch trip data if function is enabled."""
        if self._services.get('trip_statistic_v1', {}).get('active', False):
            if not await self.expired('trip_statistic_v1'):
                data = await self._connection.getTripStatistics(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch trip statistics')

    async def get_position(self):
        """Fetch position data if function is enabled."""
        if self._services.get('carfinder_v1', {}).get('active', False):
            if not await self.expired('carfinder_v1'):
                data = await self._connection.getPosition(self.vin)
                if data:
                    # Reset requests remaining to 15 if parking time has been updated
                    if data.get('findCarResponse', {}).get('parkingTimeUTC', False):
                        try:
                            newTime = data.get('findCarResponse').get('parkingTimeUTC')
                            oldTime = self.attrs.get('findCarResponse').get('parkingTimeUTC')
                            if newTime > oldTime:
                                self.requests_remaining = 15
                        except:
                            pass
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch any positional data')

    async def get_statusreport(self):
        """Fetch status data if function is enabled."""
        if self._services.get('statusreport_v1', {}).get('active', False):
            if not await self.expired('statusreport_v1'):
                data = await self._connection.getVehicleStatusData(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch status report')

    async def get_charger(self):
        """Fetch charger data if function is enabled."""
        if self._services.get('rbatterycharge_v1', {}).get('active', False):
            if not await self.expired('rbatterycharge_v1'):
                data = await self._connection.getCharger(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch charger data')
        elif self._services.get('CHARGING', {}).get('active', False):
            data = await self._connection.getCharging(self.vin)
            if data:
                self._states.update(data)
            else:
                _LOGGER.debug('Could not fetch charger data')
        else:
            self._requests.pop('charger', None)

    async def get_timerprogramming(self):
        """Fetch timer data if function is enabled."""
        if self._services.get('timerprogramming_v1', {}).get('active', False):
            if not await self.expired('timerprogramming_v1'):
                data = await self._connection.getTimers(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch timers')
        else:
            self._requests.pop('departuretimer', None)

    async def wait_for_request(self, section, request, retryCount=36):
        """Update status of outstanding requests."""
        retryCount -= 1
        if (retryCount == 0):
            _LOGGER.info(f'Timeout while waiting for result of {requestId}.')
            return 'Timeout'
        try:
            status = await self._connection.get_request_status(self.vin, section, request)
            _LOGGER.debug(f'Request ID {request}: {status}')
            if status == 'In progress':
                self._requests['state'] = 'In progress'
                time.sleep(5)
                return await self.wait_for_request(section, request)
            else:
                self._requests['state'] = status
                return status
        except Exception as error:
            _LOGGER.warning(f'Exception encountered while waiting for request status: {error}')
            return 'Exception'

  # Data set functions
   # Charging (BATTERYCHARGE)
    async def set_charger_current(self, value):
        """Set charger current"""
        if self.is_charging_supported:
            if 1 <= int(value) <= 255:
                data = {'action': {'settings': {'maxChargeCurrent': int(value)},'type': 'setSettings'}}
            else:
                _LOGGER.error(f'Set charger maximum current to {value} is not supported.')
                raise Exception(f'Set charger maximum current to {value} is not supported.')
            return await self.set_charger(data)
        else:
            _LOGGER.error('No charger support.')
            raise Exception('No charger support.')

    async def set_charger(self, action):
        """Charging actions."""
        if not self._services.get('rbatterycharge_v1', False):
            _LOGGER.info('Remote start/stop of charger is not supported.')
            raise Exception('Remote start/stop of charger is not supported.')
        if self._requests['batterycharge'].get('id', False):
            timestamp = self._requests.get('batterycharge', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('batterycharge', {}).pop('id')
            else:
                _LOGGER.debug('Charging action already in progress')
                return False
        if action in ['start', 'stop']:
            data = {'action': {'type': action}}
        elif action.get('action', {}).get('type', '') == 'setSettings':
            data = action
        else:
            _LOGGER.error(f'Invalid charger action: {action}. Must be either start or stop')
            raise Exception(f'Invalid charger action: {action}. Must be either start or stop')
        try:
            self._requests['latest'] = 'Charger'
            response = await self._connection.setCharger(self.vin, data)
            if not response:
                self._requests['batterycharge'] = {'status': 'Failed'}
                _LOGGER.error(f'Failed to {action} charging')
                raise Exception(f'Failed to {action} charging')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['batterycharge'] = {
                    'timestamp': datetime.now(),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0)
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('batterycharge', response.get('id', 0))
                self._requests['batterycharge'] = {'status': status}
                return True
        except Exception as error:
            _LOGGER.warning(f'Failed to {action} charging - {error}')
            self._requests['batterycharge'] = {'status': 'Exception'}
            raise Exception(f'Failed to {action} charging - {error}')

   # Climatisation electric/auxiliary/windows (CLIMATISATION)
    async def set_climatisation_temp(self, temperature=20):
        """Set climatisation target temp."""
        if self.is_electric_climatisation_supported or self.is_auxiliary_climatisation_supported:
            if 16 <= int(temperature) <= 30:
                temp = int((temperature+273)*10)
                data = {'action': {'settings': {'targetTemperature': temp},'type': 'setSettings'}}
            else:
                _LOGGER.error(f'Set climatisation target temp to {temperature} is not supported.')
                raise Exception(f'Set climatisation target temp to {temperature} is not supported.')
            return await self.set_climater(data)
        else:
            _LOGGER.error('No climatisation support.')
            raise Exception('No climatisation support.')

    async def set_window_heating(self, action='stop'):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            if action in ['start', 'stop']:
                data = {'action': {'type': action+'WindowHeating'}}
            else:
                _LOGGER.error(f'Window heater action "{action}" is not supported.')
                raise Exception(f'Window heater action "{action}" is not supported.')
            return await self.set_climater(data)
        else:
            _LOGGER.error('No climatisation support.')
            raise Exception('No climatisation support.')

    async def set_battery_climatisation(self, mode = False):
        """Turn on/off electric climatisation from battery."""
        if self.is_electric_climatisation_supported:
            if mode in [True, False]:
                data = {'action': {'settings': {'climatisationWithoutHVpower': mode}, 'type': 'setSettings'}}
            else:
                _LOGGER.error(f'Set climatisation without external power to "{mode}" is not supported.')
                raise Exception(f'Set climatisation without external power to "{mode}" is not supported.')
            return await self.set_climater(data)
        else:
            _LOGGER.error('No climatisation support.')
            raise Exception('No climatisation support.')

    async def set_climatisation(self, mode = 'off', spin = False):
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
                raise Exception(f'Invalid climatisation type: {mode}')
            return await self.set_climater(data, spin)
        else:
            _LOGGER.error('No climatisation support.')
            raise Exception('No climatisation support.')

    async def set_climater(self, data, spin = False):
        """Climater actions."""
        if not self._services.get('rclima_v1', False):
            _LOGGER.info('Remote control of climatisation functions is not supported.')
            raise Exception('Remote control of climatisation functions is not supported.')
        if self._requests['climatisation'].get('id', False):
            timestamp = self._requests.get('climatisation', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('climatisation', {}).pop('id')
            else:
                _LOGGER.debug('A climatisation action is already in progress')
                return False
        try:
            self._requests['latest'] = 'Climatisation'
            response = await self._connection.setClimater(self.vin, data, spin)
            if not response:
                self._requests['climatisation'] = {'status': 'Failed'}
                _LOGGER.error('Failed to execute climatisation request')
                raise Exception('Failed to execute climatisation request')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['climatisation'] = {
                    'timestamp': datetime.now(),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('climatisation', response.get('id', 0))
                self._requests['climatisation'] = {'status': status}
                return True
        except Exception as error:
            _LOGGER.warning(f'Failed to execute climatisation request - {error}')
            self._requests['climatisation'] = {'status': 'Exception'}
        raise Exception('Climatisation action failed')

   # Parking heater heating/ventilation (RS)
    async def set_pheater(self, mode, spin):
        """Set the mode for the parking heater."""
        if not self.is_pheater_heating_supported:
            _LOGGER.error('No parking heater support.')
            raise Exception('No parking heater support.')
        if self._requests['preheater'].get('id', False):
            timestamp = self._requests.get('preheater', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('preheater', {}).pop('id')
            else:
                _LOGGER.debug('A parking heater action is already in progress')
                return False
        if not mode in ['heating', 'ventilation', 'off']:
            _LOGGER.error(f'{mode} is an invalid action for parking heater')
            raise Exception(f'{mode} is an invalid action for parking heater')
        if mode == 'off':
            data = {'performAction': {'quickstop': {'active': False }}}
        else:
            data = {'performAction': {'quickstart': {'climatisationDuration': self.pheater_duration, 'startMode': mode, 'active': True }}}
        try:
            self._requests['latest'] = 'Preheater'
            response = await self._connection.setPreHeater(self.vin, data, spin)
            if not response:
                self._requests['preheater'] = {'status': 'Failed'}
                _LOGGER.error(f'Failed to set parking heater to {mode}')
                raise Exception(f'setPreHeater returned "{response}"')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['preheater'] = {
                    'timestamp': datetime.now(),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('rs', response.get('id', 0))
                self._requests['preheater'] = {'status': status}
                return True
        except Exception as error:
            _LOGGER.warning(f'Failed to set parking heater mode to {mode} - {error}')
            self._requests['preheater'] = {'status': 'Exception'}
        raise Exception('Pre-heater action failed')

   # Lock (RLU)
    async def set_lock(self, action, spin):
        """Remote lock and unlock actions."""
        if not self._services.get('rlu_v1', False):
            _LOGGER.info('Remote lock/unlock is not supported.')
            raise Exception('Remote lock/unlock is not supported.')
        if self._requests['lock'].get('id', False):
            timestamp = self._requests.get('lock', {}).get('timestamp', datetime.now() - timedelta(minutes=5))
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('lock', {}).pop('id')
            else:
                _LOGGER.debug('A lock action is already in progress')
                return False
        if action in ['lock', 'unlock']:
            data = '<rluAction xmlns="http://audi.de/connect/rlu"><action>' + action + '</action></rluAction>'
        else:
            _LOGGER.error(f'Invalid lock action: {action}')
            raise Exception(f'Invalid lock action: {action}')
        try:
            self._requests['latest'] = 'Lock'
            response = await self._connection.setLock(self.vin, data, spin)
            if not response:
                self._requests['lock'] = {'status': 'Failed'}
                _LOGGER.error(f'Failed to {action} vehicle')
                raise Exception(f'Failed to {action} vehicle')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['lock'] = {
                    'timestamp': datetime.now(),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('rlu', response.get('id', 0))
                self._requests['lock'] = {'status': status}
                return True
        except Exception as error:
            _LOGGER.warning(f'Failed to {action} vehicle - {error}')
            self._requests['lock'] = {'status': 'Exception'}
        raise Exception('Lock action failed')

   # Refresh vehicle data (VSR)
    async def set_refresh(self):
        """Wake up vehicle and update status data."""
        if not self._services.get('statusreport_v1', {}).get('active', False):
           _LOGGER.info('Data refresh is not supported.')
           raise Exception('Data refresh is not supported.')
        if self._requests['refresh'].get('id', False):
            timestamp = self._requests.get('refresh', {}).get('timestamp', datetime.now() - timedelta(minutes=5))
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('refresh', {}).pop('id')
            else:
                _LOGGER.debug('A data refresh request is already in progress')
                return False
        try:
            self._requests['latest'] = 'Refresh'
            response = await self._connection.setRefresh(self.vin)
            if not response:
                _LOGGER.error('Failed to request vehicle update')
                self._requests['refresh'] = {'status': 'Failed'}
                raise Exception('Failed to execute data refresh')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['refresh'] = {
                    'timestamp': datetime.now(),
                    'status': response.get('status', 'Unknown'),
                    'id': response.get('id', 0)
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('vsr', response.get('id', 0))
                self._requests['refresh'] = {
                    'status': status
                }
                return True
        except Exception as error:
            _LOGGER.warning(f'Failed to execute data refresh - {error}')
            self._requests['refresh'] = {'status': 'Exception'}
        raise Exception('Data refresh failed')

 #### Vehicle class helpers ####
  # Vehicle info
    @property
    def attrs(self):
        return self._states

    def has_attr(self, attr):
        return is_valid_path(self.attrs, attr)

    def get_attr(self, attr):
        return find_path(self.attrs, attr)

    async def expired(self, service):
        """Check if access to service has expired."""
        try:
            now = datetime.utcnow()
            if self._services.get(service, {}).get('expiration', False):
                expiration = self._services.get(service, {}).get('expiration', False)
                if not expiration:
                    expiration = datetime.utcnow() + timedelta(days = 1)
            else:
                _LOGGER.debug(f'Could not determine end of access for service {service}, assuming it is valid')
                expiration = datetime.utcnow() + timedelta(days = 1)
            expiration = expiration.replace(tzinfo = None)
            if now >= expiration:
                _LOGGER.warning(f'Access to {service} has expired!')
                self._discovered = False
                return True
            else:
                return False
        except:
            _LOGGER.debug(f'Exception. Could not determine end of access for service {service}, assuming it is valid')
            return False

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
        """Return true if model is supported."""
        if self.attrs.get('carportData', {}).get('modelName', False):
            return True

    @property
    def model_year(self):
        """Return model year"""
        return self.attrs.get('carportData', {}).get('modelYear', None)

    @property
    def is_model_year_supported(self):
        """Return true if model year is supported."""
        if self.attrs.get('carportData', {}).get('modelYear', False):
            return True

    @property
    def model_image(self):
        #Not implemented
        """Return model image"""
        return self.attrs.get('imageUrl')

    @property
    def is_model_image_supported(self):
        #Not implemented
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301010001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

  # Connection status
    @property
    def last_connected(self):
        """Return when vehicle was last connected to connect servers."""
        last_connected_utc = self.attrs.get('StoredVehicleDataResponse').get('vehicleData').get('data')[0].get('field')[0].get('tsCarSentUtc')
        last_connected = last_connected_utc.replace(tzinfo=timezone.utc).astimezone(tz=None)
        return last_connected.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def is_last_connected_supported(self):
        """Return when vehicle was last connected to connect servers."""
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0101010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def service_inspection(self):
        """Return time left for service inspection"""
        return - int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010004'].get('value'))

    @property
    def is_service_inspection_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010004' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def service_inspection_distance(self):
        """Return time left for service inspection"""
        return - int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010003'].get('value', 0))

    @property
    def is_service_inspection_distance_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010003' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def oil_inspection(self):
        """Return time left for service inspection"""
        return - int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010002', {}).get('value', 0))

    @property
    def is_oil_inspection_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if self.attrs.get('StoredVehicleDataResponseParsed').get('0x0203010002').get('value', None) is not None:
                    return True
        return False

    @property
    def oil_inspection_distance(self):
        """Return time left for service inspection"""
        return - int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010001',{}).get('value', 0))

    @property
    def is_oil_inspection_distance_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if self.attrs.get('StoredVehicleDataResponseParsed').get('0x0203010001').get('value', None) is not None:
                    return True
        return False

    @property
    def adblue_level(self):
        """Return adblue level."""
        return int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x02040C0001', {}).get('value', 0))

    @property
    def is_adblue_level_supported(self):
        """Return true if adblue level is supported."""
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x02040C0001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x02040C0001']:
                    if self.attrs.get('StoredVehicleDataResponseParsed')['0x02040C0001'].get('value', 0) is not None:
                        return True
        return False

  # Charger related states for EV and PHEV
    @property
    def charging(self):
        """Return battery level"""
        cstate = self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('chargingState', {}).get('content', '')
        return 1 if cstate == 'charging' else 0

    @property
    def is_charging_supported(self):
        """Return true if charging is supported"""
        if self.attrs.get('charger', False):
            if 'status' in self.attrs.get('charger', {}):
                if 'chargingStatusData' in self.attrs.get('charger')['status']:
                    if 'chargingState' in self.attrs.get('charger')['status']['chargingStatusData']:
                        return True
        elif self.attrs.get('charging', False):
            return True
        return False

    @property
    def battery_level(self):
        """Return battery level"""
        if self.attrs.get('charger', False):
            return int(self.attrs.get('charger').get('status').get('batteryStatusData').get('stateOfCharge').get('content', 0))
        elif self.attrs.get('battery', False):
            return int(self.attrs.get('battery').get('stateOfChargeInPercent'))
        else:
            return 0

    @property
    def is_battery_level_supported(self):
        """Return true if battery level is supported"""
        if self.attrs.get('charger', False):
            if 'status' in self.attrs.get('charger'):
                if 'batteryStatusData' in self.attrs.get('charger')['status']:
                    if 'stateOfCharge' in self.attrs.get('charger')['status']['batteryStatusData']:
                        return True
        elif self.attrs.get('battery', False):
            if 'stateOfChargeInPercent' in self.attrs.get('battery', {}):
                return True
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
        if self.attrs.get('charger', False):
            if 'settings' in self.attrs.get('charger', {}):
                if 'maxChargeCurrent' in self.attrs.get('charger', {})['settings']:
                    return True
            else:
                return False

    @property
    def charging_cable_locked(self):
        """Return plug locked state"""
        if self.attrs.get('charger', False):
            response = self.attrs.get('charger')['status']['plugStatusData']['lockState'].get('content',0)
            if response == 'locked':
                return True
        elif self.attrs.get('plug', False):
            response = self.attrs.get('plug', {}).get('lockState', 0)
            if response == 'Unlocked':
                return False
            else:
                return False
        else:
            return False

    @property
    def is_charging_cable_locked_supported(self):
        """Return true if plug locked state is supported"""
        if self.attrs.get('charger', False):
            if 'status' in self.attrs.get('charger', {}):
                if 'plugStatusData' in self.attrs.get('charger').get('status', {}):
                    if 'lockState' in self.attrs.get('charger')['status'].get('plugStatusData', {}):
                        return True
        elif self.attrs.get('plug', False):
            if 'lockState' in self.attrs.get('plug', {}):
                return True
        return False

    @property
    def charging_cable_connected(self):
        """Return plug locked state"""
        if self.attrs.get('charger', False):
            response = self.attrs.get('charger')['status']['plugStatusData']['plugState'].get('content',0)
            if response == 'connected':
                return False
        elif self.attrs.get('plug', False):
            response = self.attrs.get('plug').get('connectionState', 0)
            if response == 'Disconnected':
                return True
        else:
            return True

    @property
    def is_charging_cable_connected_supported(self):
        """Return true if charging cable connected is supported"""
        if self.attrs.get('charger', False):
            if 'status' in self.attrs.get('charger', {}):
                if 'plugStatusData' in self.attrs.get('charger').get('status', {}):
                    if 'plugState' in self.attrs.get('charger')['status'].get('plugStatusData', {}):
                        return True
        if self.attrs.get('plug', False):
            if 'connectionState' in self.attrs.get('plug', {}):
                return True
        return False

    @property
    def charging_time_left(self):
        """Return minutes to charing complete"""
        if self.external_power:
            if self.attrs.get('charging', {}).get('remainingToCompleteInSeconds', False):
                minutes = int(self.attrs.get('charging', {}).get('remainingToCompleteInSeconds', 0))/60
            elif self.attrs.get('charger', {}).get('status', {}).get('batteryStatusData', {}).get('remainingChargingTime', False):
                minutes = self.attrs.get('charger', {}).get('status', {}).get('batteryStatusData', {}).get('remainingChargingTime', {}).get('content', 0)
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
        if self.attrs.get('charging', {}).get('chargingType', 'Invalid') is not 'Invalid':
            return True
        else:
            return False

    @property
    def is_external_power_supported(self):
        """External power supported."""
        if self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('externalPowerSupplyState', False):
            return True
        if self.attrs.get('charging', {}).get('chargingType', False):
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
        output = {}
        try:
            if self.vehicle_moving:
                output = {
                    'lat': None,
                    'lng': None,
                    'timestamp': None
                }
            else:
                posObj = self.attrs.get('findCarResponse', {})
                lat = int(posObj.get('Position').get('carCoordinate').get('latitude'))/1000000
                lng = int(posObj.get('Position').get('carCoordinate').get('longitude'))/1000000
                parkingTime = posObj.get('parkingTimeUTC')
                output = {
                    'lat' : lat,
                    'lng' : lng,
                    'timestamp' : parkingTime
                }
        except:
            output = {
                'lat': '?',
                'lng': '?',
            }
        return output

    @property
    def is_position_supported(self):
        """Return true if carfinder_v1 service is active."""
        if self._services.get('carfinder_v1', {}).get('active', False):
        #if self.attrs.get('findCarResponse', {}).get('Position', {}).get('carCoordinate', {}).get('latitude', False):
            return True
        elif self.attrs.get('isMoving', False):
            return True

    @property
    def vehicle_moving(self):
        """Return true if vehicle is moving."""
        return self.attrs.get('isMoving', False)

    @property
    def is_vehicle_moving_supported(self):
        """Return true if vehicle supports position."""
        if self.is_position_supported:
            return True

    @property
    def parking_time(self):
        """Return timestamp of last parking time."""
        parkTime_utc = self.attrs.get('findCarResponse', {}).get('parkingTimeUTC', 'Unknown')
        parkTime = parkTime_utc.replace(tzinfo=timezone.utc).astimezone(tz=None)
        return parkTime.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def is_parking_time_supported(self):
        """Return true if vehicle parking timestamp is supported."""
        if 'parkingTimeUTC' in self.attrs.get('findCarResponse', {}):
            return True

  # Vehicle fuel level and range
    @property
    def electric_range(self):
        value = -1
        if '0x0301030008' in self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008'].get('value', 0)
        elif self.attrs.get('battery', False):
            value = int(self.attrs.get('battery', {}).get('cruisingRangeElectricInMeters', 0))/1000
        return int(value)

    @property
    def is_electric_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030008' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008']:
                    return True
        elif self.attrs.get('battery', False):
            if 'cruisingRangeElectricInMeters' in self.attrs.get('battery'):
                return True
        return False

    @property
    def combustion_range(self):
        value = -1
        if '0x0301030006' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030006']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030006'].get('value', 0)
        return int(value)

    @property
    def is_combustion_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030006' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
        return False

    @property
    def combined_range(self):
        value = -1
        if '0x0301030005' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030005']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030005'].get('value', 0)
        return int(value)

    @property
    def is_combined_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
        return False

    @property
    def fuel_level(self):
        value = -1
        if '0x030103000A' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x030103000A']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x030103000A'].get('value', 0)
        return int(value)

    @property
    def is_fuel_level_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030103000A' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
        return False

  # Climatisation settings
    @property
    def climatisation_target_temperature(self):
        """Return the target temperature from climater."""
        value = self.attrs.get('climater').get('settings').get('targetTemperature').get('content')
        if value:
            reply = float((value/10)-273)
            self._climatisation_target_temperature=reply
            return reply

    @property
    def is_climatisation_target_temperature_supported(self):
        """Return true if climatisation target temperature is supported."""
        if self.attrs.get('climater', False):
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
        if self.attrs.get('climater', False):
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
            return round(float((response/10)-273.15), 1)
        else:
            return False

    @property
    def is_outside_temperature_supported(self):
        """Return true if outside temp is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        elif status in ['heatingAuxiliary'] and climatisation_type == 'electric':
            return True
        else:
            return False

    @property
    def is_auxiliary_climatisation_supported(self):
        """Return true if vehicle has auxiliary climatisation."""
        if self._services.get('rclima_v1', False):
            functions = self._services.get('rclima_v1', {}).get('operations', [])
            #for operation in functions:
            #    if operation['id'] == 'P_START_CLIMA_AU':
            if 'P_START_CLIMA_AU' in functions:
                    return True
        return False

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

  # Parking heater, "legacy" auxiliary climatisation
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
        return self.is_pheater_heating_supported

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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301040011' in self.attrs.get('StoredVehicleDataResponseParsed', {}):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030104000E' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

  # Departure timers
   # Not yet implemented
    @property
    def schedule1(self):
        return False

    @property
    def is_schedule1_suppored(self):
        if self.attrs.get('timers', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', False):
            return True
        return False

    @property
    def schedule2(self):
        return False

    @property
    def is_schedule2_suppored(self):
        if self.attrs.get('timers', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', False):
            return True
        return False

    @property
    def schedule3(self):
        return False

    @property
    def is_schedule3_suppored(self):
        if self.attrs.get('timers', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', False):
            return True
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
        if response and type(response.get('averageSpeed', None)) in (float, int):
            return True

    @property
    def trip_last_average_electric_consumption(self):
        value = self.trip_last_entry.get('averageElectricEngineConsumption')
        return float(value/10)

    @property
    def is_trip_last_average_electric_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageElectricEngineConsumption', None)) in (float, int):
            return True

    @property
    def trip_last_average_fuel_consumption(self):
        return int(self.trip_last_entry.get('averageFuelConsumption'))/10

    @property
    def is_trip_last_average_fuel_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageFuelConsumption', None)) in (float, int):
            return True

    @property
    def trip_last_average_auxillary_consumption(self):
        return self.trip_last_entry.get('averageAuxiliaryConsumption')

    @property
    def is_trip_last_average_auxillary_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageAuxiliaryConsumption', None)) in (float, int):
            return True

    @property
    def trip_last_duration(self):
        return self.trip_last_entry.get('traveltime')

    @property
    def is_trip_last_duration_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('traveltime', None)) in (float, int):
            return True

    @property
    def trip_last_length(self):
        return self.trip_last_entry.get('mileage')

    @property
    def is_trip_last_length_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('mileage', None)) in (float, int):
            return True

    @property
    def trip_last_recuperation(self):
        #Not implemented
        return self.trip_last_entry.get('recuperation')

    @property
    def is_trip_last_recuperation_supported(self):
        #Not implemented
        response = self.trip_last_entry
        if response and type(response.get('recuperation', None)) in (float, int):
            return True

    @property
    def trip_last_total_electric_consumption(self):
        #Not implemented
        return self.trip_last_entry.get('totalElectricConsumption')

    @property
    def is_trip_last_total_electric_consumption_supported(self):
        #Not implemented
        response = self.trip_last_entry
        if response and type(response.get('totalElectricConsumption', None)) in (float, int):
            return True

  # Status of set data requests
    @property
    def refresh_action_status(self):
        """Return latest status of data refresh request."""
        return self._requests.get('refresh', {}).get('status', 'None')

    @property
    def charger_action_status(self):
        """Return latest status of charger request."""
        return self._requests.get('batterycharge', {}).get('status', 'None')

    @property
    def climater_action_status(self):
        """Return latest status of climater request."""
        return self._requests.get('climatisation', {}).get('status', 'None')

    @property
    def pheater_action_status(self):
        """Return latest status of parking heater request."""
        return self._requests.get('preheater', {}).get('status', 'None')

    @property
    def lock_action_status(self):
        """Return latest status of lock action request."""
        return self._requests.get('lock', {}).get('status', 'None')

  # Requests data
    @property
    def refresh_data(self):
        """Get state of data refresh"""
        if self._requests.get('refresh', {}).get('id', False):
            return True

    @property
    def is_refresh_data_supported(self):
        """Data refresh is always supported."""
        return True

    @property
    def request_in_progress(self):
        """Request in progress is always supported."""
        try:
            for section in self._requests:
                if self._requests[section].get('id', False):
                    return True
        except:
            pass
        return False

    @property
    def is_request_in_progress_supported(self):
        """Request in progress is always supported."""
        return True

    @property
    def request_results(self):
        """Get last request result."""
        data = {}
        data['latest'] = self._requests.get('latest', None)
        data['state'] = self._requests.get('state', None)
        for section in self._requests:
            if section in ['departuretimer', 'batterycharge', 'climatisation', 'refresh', 'lock', 'preheater']:
                data[section] = self._requests[section].get('status', 'Unknown')
        return data

    @property
    def is_request_results_supported(self):
        """Request results is supported if in progress is supported."""
        return self.is_request_in_progress_supported

    @property
    def requests_remaining(self):
        """Get remaining requests before throttled."""
        if self.attrs.get('rate_limit_remaining', False):
            self.requests_remaining = self.attrs.get('rate_limit_remaining')
            self.attrs.pop('rate_limit_remaining')
        return self._requests['remaining']

    @requests_remaining.setter
    def requests_remaining(self, value):
        self._requests['remaining'] = value

    @property
    def is_requests_remaining_supported(self):
        return True if self._requests.get('remaining', False) else False

 #### Helper functions ####
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
