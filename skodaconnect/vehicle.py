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
from skodaconnect.exceptions import (
    SkodaConfigException,
    SkodaException,
    SkodaEULAException,
    SkodaServiceUnavailable,
    SkodaThrottledException,
    SkodaInvalidRequestException,
    SkodaRequestInProgressException
)

_LOGGER = logging.getLogger(__name__)

DATEZERO = datetime(1970,1,1)
class Vehicle:
    def __init__(self, conn, data):
        _LOGGER.debug(f'Creating Vehicle class object with data {data}')
        self._connection = conn
        self._url = data.get('vin', '')
        self._connectivities = data.get('connectivities', '')
        self._capabilities = data.get('capabilities', [])
        self._specification = data.get('specification', {})
        self._homeregion = 'https://msg.volkswagen.de'
        self._modelimagel = None
        self._modelimages = None
        self._discovered = False
        self._dashboard = None
        self._states = {}

        self._requests = {
            'departuretimer': {'status': 'N/A', 'timestamp': DATEZERO},
            'batterycharge': {'status': 'N/A', 'timestamp': DATEZERO},
            'climatisation': {'status': 'N/A', 'timestamp': DATEZERO},
            'air-conditioning': {'status': 'N/A', 'timestamp': DATEZERO},
            'refresh': {'status': 'N/A', 'timestamp': DATEZERO},
            'lock': {'status': 'N/A', 'timestamp': DATEZERO},
            'honkandflash': {'status': 'N/A', 'timestamp': DATEZERO},
            'preheater': {'status': 'N/A', 'timestamp': DATEZERO},
            'remaining': -1,
            'latest': 'N/A',
            'state': 'N/A'
        }
        self._climate_duration = 30

        # API Endpoints that might be enabled for car (that we support)
        self._services = {}
        # VW-Group API connectivity is enabled
        if 'ONLINE' in self._connectivities:
            self._services.update({
                'rheating_v1': {'active': False},
                'rclima_v1': {'active': False},
                'rlu_v1': {'active': False},
                'trip_statistic_v1': {'active': False},
                'statusreport_v1': {'active': False},
                'rbatterycharge_v1': {'active': False},
                'rhonk_v1': {'active': False},
                'carfinder_v1': {'active': False},
                'timerprogramming_v1': {'active': False},
            })
        # Skoda Native API connectivity is enabled
        elif 'REMOTE' in self._connectivities:
            self._services.update({
                'STATE': {'active': False},
                'CHARGING': {'active': False},
                'AIR_CONDITIONING': {'active': False},
                'PARKING_POSITION': {'active': False},
            })
        # SmartLink connectivity is enabled
        elif 'INCAR' in self._connectivities:
            self._services.update({
                'vehicle_status': {'active': True}
            })
        # No supported connectivity types found
        else:
            self._services = {}

 #### API get and set functions ####
  # Init and update vehicle data
    async def discover(self):
        """Discover vehicle and initial data."""
        # For VW-Group API
        if 'ONLINE' in self._connectivities:
            _LOGGER.debug(f'Starting discovery for vehicle {self.vin}')
            homeregion = await self._connection.getHomeRegion(self.vin)
            _LOGGER.debug(f'Get homeregion for VIN {self.vin}')
            if homeregion:
                self._homeregion = homeregion

            await asyncio.gather(
                self.get_realcardata(),
                return_exceptions=True
            )
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
                                data['active'] = True
                                if service.get('cumulatedLicense', {}).get('expirationDate', False):
                                    data['expiration'] = service.get('cumulatedLicense', {}).get('expirationDate', None).get('content', None)
                                if service.get('operation', False):
                                    data.update({'operations': []})
                                    for operation in service.get('operation', []):
                                        data['operations'].append(operation.get('id', None))
                                _LOGGER.debug(f'Discovered active supported service: {serviceName}, licensed until {data.get("expiration").strftime("%Y-%m-%d %H:%M:%S")}')
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
            if self._connection._session_fulldebug:
                for endpointName, endpoint in self._services.items():
                    if endpoint.get('active', False):
                        _LOGGER.debug(f'API endpoint "{endpointName}" valid until {endpoint.get("expiration").strftime("%Y-%m-%d %H:%M:%S")} - operations: {endpoint.get("operations", [])}')

        # For Skoda native API
        elif 'REMOTE' in self._connectivities:
            for service in self._services:
                for capability in self._capabilities:
                    if capability == service:
                        self._services[service]['active'] = True
        # For ONLY SmartLink capability
        elif 'INCAR' in self._connectivities:
            self._services = {'vehicle_status': {'active': True}}
        else:
            self._services = {}

        # Get URLs for model image
        self._modelimagel = await self.get_modelimageurl(size='L')
        self._modelimages = await self.get_modelimageurl(size='S')

        self._discovered = datetime.now()

    async def update(self):
        """Try to fetch data for all known API endpoints."""
        # Update vehicle information if not discovered or stale information
        if not self._discovered:
            await self.discover()
        else:
            # Rediscover if data is older than 1 hour
            hourago = datetime.now() - timedelta(hours = 1)
            if self._discovered < hourago:
                await self.discover()

        # Fetch all data if car is not deactivated
        if not self.deactivated:
            try:
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
            except:
                raise SkodaException("Update failed")
            return True
        else:
            _LOGGER.info(f'Vehicle with VIN {self.vin} is deactivated.')
            return False
        return True

  # Data collection functions
    async def get_modelimageurl(self, size='L'):
        """Fetch the URL for model image."""
        return await self._connection.getModelImageURL(self.vin, size)

    async def get_realcardata(self):
        """Fetch realcar data."""
        data = await self._connection.getRealCarData()
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
            self._requests.pop('air-conditioning', None)
        elif self._services.get('AIR_CONDITIONING', {}).get('active', False):
            data = await self._connection.getAirConditioning(self.vin)
            if data:
                self._states.update(data)
            else:
                _LOGGER.debug('Could not fetch air conditioning data')
            self._requests.pop('climatisation', None)
        # If not supported, remove from "requests" dict
        else:
            self._requests.pop('air-conditioning', None)
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
        elif self._services.get('PARKING_POSITION', {}).get('active', False):
            data = await self._connection.getParkingPosition(self.vin)
            if data:
                self._states.update(data)
            else:
                _LOGGER.debug('Could not fetch charger data')
        else:
            self._requests.pop('charger', None)

    async def get_statusreport(self):
        """Fetch status data if function is enabled."""
        if self._services.get('statusreport_v1', {}).get('active', False):
            if not await self.expired('statusreport_v1'):
                data = await self._connection.getVehicleStatusReport(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch status report')
        elif self._services.get('STATE', {}).get('active', False):
            data = await self._connection.getVehicleStatus(self.vin)
            if data:
                self._states.update(data)
            else:
                _LOGGER.debug('Could not fetch status report')
        elif self._services.get('vehicle_status', {}).get('active', False):
            data = await self._connection.getVehicleStatus(self.vin, smartlink=True)
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
                data = await self._connection.getDeparturetimer(self.vin)
                if data:
                    self._states.update(data)
                else:
                    _LOGGER.debug('Could not fetch timers')
        elif self._services.get('AIR_CONDITIONING', {}).get('active', False):
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
            _LOGGER.info(f'Timeout while waiting for result of {request}.')
            return 'Timeout'
        try:
            status = await self._connection.get_request_status(self.vin, section, request)
            _LOGGER.info(f'Request for {section} with ID {request}: {status}')
            if status == 'In progress':
                self._requests['state'] = 'In progress'
                await asyncio.sleep(5)
                return await self.wait_for_request(section, request, retryCount)
            else:
                self._requests['state'] = status
                return status
        except Exception as error:
            _LOGGER.warning(f'Exception encountered while waiting for request status: {error}')
            return 'Exception'

  # Data set functions
   # API endpoint charging
    async def set_charger_current(self, value):
        """Set charger current"""
        if self.is_charging_supported:
            # Set charger max ampere to integer value
            if isinstance(value, int):
                if 1 <= int(value) <= 255:
                    # VW-Group API charger current request
                    if self._services.get('rbatterycharge_v1', False) is not False:
                        data = {'action': {'settings': {'maxChargeCurrent': int(value)}, 'type': 'setSettings'}}
                    # Skoda Native API charger current request, does this work?
                    elif self._services.get('CHARGING', False) is not False:
                        data = {'chargingSettings': {
                                'autoUnlockPlugWhenCharged': self.attrs.get('chargerSettings', {}).get('autoUnlockPlugWhenCharged', 'Off'),
                                'maxChargeCurrentAc': value,
                                'targetStateOfChargeInPercent': self.attrs.get('chargerSettings', {}).get('targetStateOfChargeInPercent', 100)},
                            'type': 'UpdateSettings'
                        }
                else:
                    _LOGGER.error(f'Set charger maximum current to {value} is not supported.')
                    raise SkodaInvalidRequestException(f'Set charger maximum current to {value} is not supported.')
            # Mimick app and set charger max ampere to Maximum/Reduced
            elif isinstance(value, str):
                if value in ['Maximum', 'maximum', 'Max', 'max', 'Minimum', 'minimum', 'Min', 'min', 'Reduced', 'reduced']:
                    # VW-Group API charger current request
                    if self._services.get('rbatterycharge_v1', False) is not False:
                        value = 254 if value in ['Maximum', 'maximum', 'Max', 'max'] else 252
                        data = {'action': {'settings': {'maxChargeCurrent': int(value)}, 'type': 'setSettings'}}
                    # Skoda Native API charger current request
                    elif self._services.get('CHARGING', False) is not False:
                        value = 'Maximum' if value in ['Maximum', 'maximum', 'Max', 'max'] else 'Reduced'
                        data = {'chargingSettings': {
                                'autoUnlockPlugWhenCharged': self.attrs.get('chargerSettings', {}).get('autoUnlockPlugWhenCharged', 'Off'),
                                'maxChargeCurrentAc': value,
                                'targetStateOfChargeInPercent': self.attrs.get('chargerSettings', {}).get('targetStateOfChargeInPercent', 100)},
                            'type': 'UpdateSettings'
                        }
                else:
                    _LOGGER.error(f'Set charger maximum current to {value} is not supported.')
                    raise SkodaInvalidRequestException(f'Set charger maximum current to {value} is not supported.')
            else:
                _LOGGER.error(f'Data type passed is invalid.')
                raise SkodaInvalidRequestException(f'Invalid data type.')
            return await self.set_charger(data)
        else:
            _LOGGER.error('No charger support.')
            raise SkodaInvalidRequestException('No charger support.')

    async def set_plug_autounlock(self, setting='Off'):
        """Set charger plug auto unlock setting."""
        data = {}
        if setting in ['Permanent', 'Off']:
            data = {
                'chargingSettings': {
                    'autoUnlockPlugWhenCharged': setting,
                    'maxChargeCurrentAc': self.charge_max_ampere,
                    'targetStateOfChargeInPercent': self.min_charge_level
                },
                'type': 'UpdateSettings'
            }
        else:
            raise SkodaInvalidRequestException('Invalid setting for plug auto unlock.')
        return await self.set_charger(data)

    async def set_charger(self, action):
        """Charging actions."""
        if not self._services.get('rbatterycharge_v1', False) and not self._services.get('CHARGING', False):
            _LOGGER.info('Remote start/stop of charger is not supported.')
            raise SkodaInvalidRequestException('Remote start/stop of charger is not supported.')
        if self._requests['batterycharge'].get('id', False):
            timestamp = self._requests.get('batterycharge', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('batterycharge', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('Charging action already in progress')
        # VW-Group API requests
        if self._services.get('rbatterycharge_v1', False):
            if action in ['start', 'Start', 'On', 'on']:
                data = {'action': {'type': 'start'}}
            elif action in ['stop', 'Stop', 'Off', 'off']:
                data = {'action': {'type': 'stop'}}
            elif isinstance(action.get('action', None), dict):
                data = action
            else:
                _LOGGER.error(f'Invalid charger action: {action}. Must be either start, stop or setSettings')
                raise SkodaInvalidRequestException(f'Invalid charger action: {action}. Must be either start, stop or setSettings')
        # Skoda Native API requests
        if self._services.get('CHARGING', False):
            if action in ['start', 'stop']:
                data = {'type': action.capitalize()}
            elif action.get('action', {}) == 'chargelimit':
                data = {'chargingSettings': {
                            'autoUnlockPlugWhenCharged': self.attrs.get('chargerSettings', {}).get('autoUnlockPlugWhenCharged', 'Off'),
                            'maxChargeCurrentAc': self.charge_max_ampere,
                            'targetStateOfChargeInPercent': action.get('limit', 50)},
                        'type': 'UpdateSettings'
                }
            elif action.get('type', {}) == 'UpdateSettings':
                data = action
                pass
            else:
                _LOGGER.error(f'Invalid charger action: {action}. Must be one of start, stop or data for updating settings')
                raise SkodaInvalidRequestException(f'Invalid charger action: {action}. Must be one of start, stop or data for set chargelimit')
        try:
            self._requests['latest'] = 'Charger'
            if self._services.get('rbatterycharge_v1', False):
                response = await self._connection.setCharger(self.vin, data)
            elif self._services.get('CHARGING', False):
                response = await self._connection.setCharging(self.vin, data)
            if not response:
                self._requests['batterycharge']['status'] = 'Failed'
                _LOGGER.error(f'Failed to {action} charging')
                raise SkodaException(f'Failed to {action} charging')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['batterycharge'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0)
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    if self._services.get('rbatterycharge_v1', False):
                        status = await self.wait_for_request('batterycharge', response.get('id', 0))
                    elif self._services.get('CHARGING', False):
                        status = await self.wait_for_request('charging', response.get('id', 0))
                self._requests['batterycharge']['status'] = status
                self._requests['batterycharge'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to {action} charging - {error}')
            self._requests['batterycharge']['status'] = 'Exception'
            raise SkodaException(f'Failed to execute set charger - {error}')

   # API endpoint departuretimer
    async def set_charge_limit(self, limit=50):
        """ Set charging limit. """
        if not self._services.get('timerprogramming_v1', False) and not self._services.get('CHARGING', False):
            _LOGGER.info('Set charging limit is not supported.')
            raise SkodaInvalidRequestException('Set charging limit is not supported.')
        data = {}
        # VW-Group API charging
        if self._services.get('timerprogramming_v1', False) is not False:
            if isinstance(limit, int):
                if limit in [0, 10, 20, 30, 40, 50]:
                    data['limit'] = limit
                    data['action'] = 'chargelimit'
                else:
                    raise SkodaInvalidRequestException(f'Charge limit must be one of 0, 10, 20, 30, 40 or 50.')
            else:
                raise SkodaInvalidRequestException(f'Charge limit "{limit}" is not supported.')
            return await self._set_timers(data)
        # Skoda Native API charging
        elif self._services.get('CHARGING', False) is not False:
            if isinstance(limit, int):
                if limit in [50, 60, 70, 80, 90, 100]:
                    data['limit'] = limit
                    data['action'] = 'chargelimit'
                else:
                    raise SkodaInvalidRequestException(f'Charge limit must be one of 50, 60, 70, 80, 90 or 100.')
            else:
                raise SkodaInvalidRequestException(f'Charge limit "{limit}" is not supported.')
            return await self.set_charger(data)

    async def set_timer_active(self, id=1, action='off'):
        """ Activate/deactivate departure timers. """
        data = {}
        supported = 'is_departure' + str(id) + "_supported"
        if getattr(self, supported) is not True:
            raise SkodaConfigException(f'This vehicle does not support timer id "{id}".')
        # VW-Group API
        if self._services.get('timerprogramming_v1', False):
            data['id'] = id
            if action in ['on', 'off']:
                data['action'] = action
            else:
                raise SkodaInvalidRequestException(f'Timer action "{action}" is not supported.')
            return await self._set_timers(data)
        # Skoda native API
        elif self._services.get('AIR_CONDITIONING', False):
            if action in ['on', 'off']:
                try:
                    # First get most recent departuretimer settings from server
                    timers = await self._connection.getTimers(self.vin)
                    # Prepare data for request method
                    data = {'type': 'UpdateTimers', 'timersSettings': {'timers': []}}
                    if timers:
                        data['timersSettings']['timers'] = timers.get('timers', [])
                    else:
                        raise SkodaException("Failed to fetch current timer settings")
                    for timer in data['timersSettings']['timers']:
                        _LOGGER.debug(f"Matching id {id} to {timer}")
                        if timer.get('id', None) == id:
                            index = data['timersSettings']['timers'].index(timer)
                            data['timersSettings']['timers'][index]['enabled'] = True if action == 'on' else False
                            return await self._set_aircon(data)
                except Exception as e:
                    _LOGGER.debug(f"Exception: {e}")
                    pass
                raise SkodaInvalidRequestException(f'Timer action "{action}" failed. ')
            else:
                raise SkodaInvalidRequestException(f'Timer action "{action}" is not supported.')
        else:
            raise SkodaInvalidRequestException('Departure timers are not supported.')

    async def set_heatersource(self, source='electric', spin=None):
        """ Activate/deactivate use of aux heater for departure timers. """
        """ VW-Group API only for PHEV vehicles """
        data = {}
        if not self.is_auxiliary_climatisation_supported:
            raise SkodaInvalidRequestException('Auxiliary heater is not supprted on this vehicle.')
        if spin is None:
            raise SkodaInvalidRequestException('SPIN is required to set heater source.')

        # VW-Group API
        if self._services.get('timerprogramming_v1', False):
            if source.lower() in ['electric', 'automatic']:
                data = {
                    'heaterSource': source.lower(),
                    'action': 'heaterSource',
                    'spin': spin
                }
            else:
                raise SkodaInvalidRequestException(f'Source "{action}" is not supported as heater source.')
            return await self._set_timers(data)
        else:
            raise SkodaInvalidRequestException('Departure timers are not supported.')

    async def set_timer_schedule(self, id, schedule={}, spin=False):
        """ Set departure schedules. """
        data = {}
        # Validate required user inputs
        supported = 'is_departure' + str(id) + "_supported"
        if getattr(self, supported) is not True:
            raise SkodaConfigException(f'Timer id "{id}" is not supported for this vehicle.')
        else:
            _LOGGER.debug(f'Timer id {id} is supported')
        # Verify that needed data is supplied
        if not schedule:
            raise SkodaInvalidRequestException('A schedule must be set.')
        if not isinstance(schedule.get('enabled', ''), bool):
            raise SkodaInvalidRequestException('The enabled variable must be set to True or False.')
        if not isinstance(schedule.get('recurring', ''), bool):
            raise SkodaInvalidRequestException('The recurring variable must be set to True or False.')
        if not re.match('^[0-9]{2}:[0-9]{2}$', schedule.get('time', '')):
            raise SkodaInvalidRequestException('The time for departure must be set in 24h format HH:MM.')

        # Validate optional inputs
        if schedule.get('recurring', False):
            if not re.match('^[yn]{7}$', schedule.get('days', '')):
                raise SkodaInvalidRequestException('For recurring schedules the days variable must be set to y/n mask (mon-sun with only wed enabled): nnynnnn.')
        elif not schedule.get('recurring'):
            if not re.match('^[0-9]{4}-[0-9]{2}-[0-9]{2}$', schedule.get('date', '')):
                raise SkodaInvalidRequestException('For single departure schedule the date variable must be set to YYYY-mm-dd.')
        if not schedule.get('heaterSource', False):
            if not schedule.get('heaterSource', None) in ['automatic', 'electric']:
                raise SkodaInvalidRequestException('Heater source must be one of "electric" or "automatic".')
        elif spin is False:
            if schedule.get('heaterSource', None) == 'automatic':
                raise SkodaInvalidRequestException('SPIN must be supplied when using auxiliary heater".')

        # VW-Group API
        if self._services.get('timerprogramming_v1', False):
            # Validate options only available for VW-Group API
            # Sanity check for off-peak hours
            if not isinstance(schedule.get('nightRateActive', False), bool):
                raise SkodaInvalidRequestException('The off-peak active variable must be set to True or False')
            if schedule.get('nightRateStart', None) is not None:
                if not re.match('^[0-9]{2}:[0-9]{2}$', schedule.get('nightRateStart', '')):
                    raise SkodaInvalidRequestException('The start time for off-peak hours must be set in 24h format HH:MM.')
            if schedule.get('nightRateEnd', None) is not None:
                if not re.match('^[0-9]{2}:[0-9]{2}$', schedule.get('nightRateEnd', '')):
                    raise SkodaInvalidRequestException('The start time for off-peak hours must be set in 24h format HH:MM.')

            # Check if charging/climatisation is set and correct
            if not isinstance(schedule.get('operationClimatisation', False), bool):
                raise SkodaInvalidRequestException('The climatisation enable variable must be set to True or False')
            if not isinstance(schedule.get('operationCharging', False), bool):
                raise SkodaInvalidRequestException('The charging variable must be set to True or False')

            # Validate temp setting, if set
            if schedule.get("targetTemp", None) is not None:
                if not 16 <= float(schedule.get("targetTemp", None)) <= 30:
                    raise SkodaInvalidRequestException('Target temp must be integer value from 16 to 30')
                else:
                    data['temp'] = schedule.get('targetTemp')

            # Validate charge target and current
            if schedule.get("targetChargeLevel", None) is not None:
                if not 0 <= int(schedule.get("targetChargeLevel", None)) <= 100:
                    raise SkodaInvalidRequestException('Target charge level must be 0 to 100')
            if schedule.get("chargeMaxCurrent", None) is not None:
                if isinstance(schedule.get('chargeMaxCurrent', None), str):
                    if not schedule.get("chargeMaxCurrent", None) in ['Maximum', 'maximum', 'Max', 'max', 'Minimum', 'minimum', 'Min', 'min', 'Reduced', 'reduced']:
                        raise SkodaInvalidRequestException('Charge current must be one of Maximum/Minimum/Reduced')
                    elif 'ONLINE' in self._connectivities:
                        # Set string to numeric value for VW-Group API
                        schedule['chargeMaxCurrent'] = 252
                        if schedule.get("chargeMaxCurrent", None) in ['Maximum', 'maximum', 'Max', 'max']: schedule['chargeMaxCurrent'] = 254
                elif isinstance(schedule.get('chargeMaxCurrent', None), int):
                    if not 1 <= int(schedule.get("chargeMaxCurrent", 254)) < 255:
                        raise SkodaInvalidRequestException('Charge current must be set from 1 to 254')
                else:
                    raise SkodaInvalidRequestException('Invalid type for charge max current variable')
            # Prepare data and execute
            data['id'] = id
            data['action'] = 'schedule'
            data['schedule'] = schedule
            data['spin'] = spin
            return await self._set_timers(data)

        # Skoda native API
        elif self._services.get('AIR_CONDITIONING', False):
            try:
                # First get most recent departuretimer settings from server
                timers = await self._connection.getTimers(self.vin)
                # Prepare data for request method
                data = {'type': 'UpdateTimers', 'timersSettings': {'timers': []}}
                weekdays = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
                if timers.get('timers', False):
                    data['timersSettings']['timers'] = timers.get('timers', [])
                else:
                    raise SkodaException("Failed to fetch current timer settings")
                for timer in data['timersSettings']['timers']:
                    if timer.get('id', None) == id:
                        index = data['timersSettings']['timers'].index(timer)
                        data['timersSettings']['timers'][index]['enabled'] = schedule.get('enabled')
                        data['timersSettings']['timers'][index]['time'] = schedule.get('time')
                        if schedule.get('recurring'):
                            data['timersSettings']['timers'][index]['type'] = 'RECURRING'
                            data['timersSettings']['timers'][index]['recurringOn'] = []
                            days = schedule.get('days', 'nnnnnnn')
                            for num in range(0, 7):
                                if days[num] == 'y':
                                    data['timersSettings']['timers'][index]['recurringOn'].append(weekdays[num])
                        else:
                            data['timersSettings']['timers'][index]['type'] = 'ONE_OFF'
                            data['timersSettings']['timers'][index]['date'] = schedule.get('date')
                        return await self._set_aircon(data)
            except Exception as e:
                _LOGGER.debug(f"Exception: {e}")
                pass
            raise SkodaInvalidRequestException(f'Timer action failed. ')
        else:
            _LOGGER.info('Departure timers are not supported.')
            raise SkodaInvalidRequestException('Departure timers are not supported.')

    async def _set_timers(self, data=None):
        """ Set departure timers. """
        if not self._services.get('timerprogramming_v1', False):
            raise SkodaInvalidRequestException('Departure timers are not supported.')
        if self._requests['departuretimer'].get('id', False):
            timestamp = self._requests.get('departuretimer', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('departuretimer', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('Scheduling of departure timer is already in progress')
        # Verify temperature setting
        if data.get('temp', False):
            if data['temp'] in {16,16.5,17,17.5,18,18.5,19,19.5,20,20.5,21,21.5,22,22.5,23,23.5,24,24.5,25,25.5,26,26.5,27,27.5,28,28.5,29,29.5,30}:
                data['temp'] = int((data['temp'] + 273) * 10)
            else:
                data['temp'] = int((int(data['temp']) + 273) * 10)
        else:
            try:
                data['temp'] = int((self.climatisation_target_temperature + 273) * 10)
            except:
                data['temp'] = 2930
                pass
        if 2890 <= data['temp'] <= 3030:
            pass
        else:
            data['temp'] = 2930

        try:
            self._requests['latest'] = 'Departuretimer'
            response = await self._connection.setDeparturetimer(self.vin, data, spin=data.get('spin', False))
            if not response:
                self._requests['departuretimer']['status'] = 'Failed'
                _LOGGER.error('Failed to execute departure timer request')
                raise SkodaException('Failed to execute departure timer request')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['departuretimer'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('departuretimer', response.get('id', 0))
                self._requests['departuretimer']['status'] = status
                self._requests['departuretimer'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to execute departure timer request - {error}')
            self._requests['departuretimer']['status'] = 'Exception'
        raise SkodaException('Failed to set departure timer schedule')

   # Climatisation electric/auxiliary/windows (CLIMATISATION)
    async def set_climatisation_temp(self, temperature=20):
        """Set climatisation target temp."""
        if self.is_electric_climatisation_supported or self.is_auxiliary_climatisation_supported:
            if 16 <= float(temperature) <= 30:
                temp = int((temperature + 273) * 10)
                data = {'action': {'settings': {'targetTemperature': temp}, 'type': 'setSettings'}}
            else:
                _LOGGER.error(f'Set climatisation target temp to {temperature} is not supported.')
                raise SkodaInvalidRequestException(f'Set climatisation target temp to {temperature} is not supported.')
            return await self._set_climater(data)
        else:
            _LOGGER.error('No climatisation support.')
            raise SkodaInvalidRequestException('No climatisation support.')

    async def set_window_heating(self, action = 'stop'):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            if action in ['start', 'stop']:
                # Check if this is a Skoda native API vehicle
                if self._services.get('AIR_CONDITIONING', False):
                    if action in ['start', 'stop']:
                        data = {
                            'type': action,
                            'section': 'WindowHeating'
                        }
                        return await self._set_aircon(data)
                    elif action in ['enabled', 'disabled']:
                        setting = True if action == 'enabled' else False
                        if self.attrs.get('airConditioningSettings', False):
                            data = self.attrs.get('airConditioningSettings')
                        else:
                            _LOGGER.warning('Could not find stored climatisation settings, using defaults.')
                            data['airConditioningSettings'] = {
                                'targetTemperatureInKelvin': 294.15,
                                'windowHeatingEnabled': False,
                                'airConditioningAtUnlock': False,
                                'zonesSettings': {
                                    'frontLeftEnabled': False,
                                    'frontRightEnabled': False
                                }
                            }
                        data['airConditioningSettings']['windowHeatingEnabled'] = setting
                    return await self._set_aircon(data)
                else:
                    # Vehicle is hosted by VW-Group API
                    data = {'action': {'type': action + 'WindowHeating'}}
                    return await self._set_climater(data)
            else:
                _LOGGER.error(f'Window heater action "{action}" is not supported.')
                raise SkodaInvalidRequestException(f'Window heater action "{action}" is not supported.')
        else:
            _LOGGER.error('No climatisation support.')
            raise SkodaInvalidRequestException('No climatisation support.')

    async def set_battery_climatisation(self, mode = False):
        """Turn on/off electric climatisation from battery."""
        if self.is_electric_climatisation_supported:
            if mode in [True, False]:
                data = {'action': {'settings': {'climatisationWithoutHVpower': mode}, 'type': 'setSettings'}}
            else:
                _LOGGER.error(f'Set climatisation without external power to "{mode}" is not supported.')
                raise SkodaInvalidRequestException(f'Set climatisation without external power to "{mode}" is not supported.')
            return await self._set_climater(data)
        else:
            _LOGGER.error('No climatisation support.')
            raise SkodaInvalidRequestException('No climatisation support.')

    async def set_climatisation(self, mode = 'off', temp = None, hvpower = None, spin = None):
        """Turn on/off climatisation with electric/auxiliary heater."""
        data = {}
        # Validate user input
        if mode not in ['electric', 'auxiliary', 'Start', 'Stop', 'on', 'off']:
            raise SkodaInvalidRequestException(f"Invalid mode for set_climatisation: {mode}")
        elif mode == 'auxiliary' and spin is None:
            raise SkodaInvalidRequestException("Starting auxiliary heater requires provided S-PIN")
        if temp is not None:
            if not isinstance(temp, float):
                raise SkodaInvalidRequestException(f"Invalid type for temp")
            elif not 16 <= float(temp) <=30:
                raise SkodaInvalidRequestException(f"Invalid value for temp")
        else:
            temp = self.climatisation_target_temperature
        if hvpower is not None:
            if not isinstance(hvpower, bool):
                raise SkodaInvalidRequestException(f"Invalid type for hvpower")
        if self.is_electric_climatisation_supported:
            if self._services.get('rclima_v1', False):
                if mode in ['Start', 'start', 'On', 'on']:
                    mode = 'electric'
                if mode in ['electric', 'auxiliary']:
                    targetTemp = int((temp + 273) * 10)
                    if hvpower is not None:
                        withoutHVPower = hvpower
                    else:
                        withoutHVPower = self.climatisation_without_external_power
                    data = {
                        'action':{
                            'settings':{
                                'climatisationWithoutHVpower': withoutHVPower,
                                'targetTemperature': targetTemp,
                                'heaterSource': mode
                            },
                            'type': 'startClimatisation'
                        }
                    }
                else:
                    data = {'action': {'type': 'stopClimatisation'}}
                return await self._set_climater(data, spin)
            elif self._services.get('AIR_CONDITIONING', False):
                if mode == 'auxiliary':
                    raise SkodaInvalidRequestException('No auxiliary climatisation support.')
                if mode in ['Start', 'start', 'On', 'on', 'electric']:
                    # Fetch current climatisation settings
                    airconData = await self._connection.getAirConditioning(self.vin)
                    if airconData:
                        airconData.pop('airConditioning', None)
                        data = airconData
                    else:
                        # Try to use saved configuration from previous poll, else use defaults
                        if self.attrs.get('airConditioningSettings', False):
                            _LOGGER.warning('Failed to fetch climatisation settings, using saved values.')
                            data = self.attrs.get('airConditioningSettings')
                        else:
                            _LOGGER.warning('Could not fetch climatisation settings, using defaults.')
                            data['airConditioningSettings'] = {
                                'targetTemperatureInKelvin': 294.15,
                                'windowHeatingEnabled': False,
                                'airConditioningAtUnlock': False,
                                'zonesSettings': {
                                    'frontLeftEnabled': False,
                                    'frontRightEnabled': False
                                }
                            }
                    data.pop('temperatureConversionTableUsed', None)
                    data['type'] = 'Start'
                    if temp is not None:
                        data['airConditioningSettings']['targetTemperatureInKelvin'] = temp + 273.15
                else:
                    data = {'type': 'Stop'}
                return await self._set_aircon(data)
        else:
            _LOGGER.error('No climatisation support.')
        raise SkodaInvalidRequestException('No climatisation support.')

    async def _set_climater(self, data, spin = False):
        """Climater actions."""
        if not self._services.get('rclima_v1', False):
            _LOGGER.info('Remote control of climatisation functions is not supported.')
            raise SkodaInvalidRequestException('Remote control of climatisation functions is not supported.')
        if self._requests['climatisation'].get('id', False):
            timestamp = self._requests.get('climatisation', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('climatisation', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('A climatisation action is already in progress')
        try:
            self._requests['latest'] = 'Climatisation'
            response = await self._connection.setClimater(self.vin, data, spin)
            if not response:
                self._requests['climatisation']['status'] = 'Failed'
                _LOGGER.error('Failed to execute climatisation request')
                raise SkodaException('Failed to execute climatisation request')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['climatisation'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('climatisation', response.get('id', 0))
                self._requests['climatisation']['status'] = status
                self._requests['climatisation'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to execute climatisation request - {error}')
            self._requests['climatisation']['status'] = 'Exception'
        raise SkodaException('Climatisation action failed')

    async def _set_aircon(self, data, spin = False):
        """Air conditioning actions."""
        if not self._services.get('AIR_CONDITIONING', False):
            _LOGGER.info('Remote control of air conditioning functions is not supported.')
            raise SkodaInvalidRequestException('Remote control of air conditioning functions is not supported.')
        if self._requests['air-conditioning'].get('id', False):
            timestamp = self._requests.get('air-conditioning', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('air-conditioning', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('Air conditioning action is already in progress')
        try:
            _LOGGER.debug(f'Attempting to update aircon settings with data {data}.')
            if 'UpdateTimers' in data['type']:
                self._requests['latest'] = 'Timers'
            elif 'UpdateSettings' in data['type']:
                self._requests['latest'] = 'Climatisation settings'
            elif data['type'] in ['Start', 'Stop']:
                self._requests['latest'] = 'Climatisation'
            else:
                self._requests['latest'] = 'Air conditioning'
            _LOGGER.debug('Sending request')
            # Special handling for window heating
            if data['section'] == 'WindowHeating':
                response = await self._connection.setWindowHeater(self.vin, data.get('type', 'Stop'))
            else:
                response = await self._connection.setAirConditioning(self.vin, data)
            if not response:
                self._requests['air-conditioning']['status'] = 'Failed'
                _LOGGER.error('Failed to execute air conditioning request')
                raise SkodaException('Failed to execute air conditioning request')
            else:
                #self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['air-conditioning'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('air-conditioning', response.get('id', 0))
                self._requests['air-conditioning']['status'] = status
                self._requests['air-conditioning'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to execute air conditioning request - {error}')
            self._requests['air-conditioning']['status'] = 'Exception'
        raise SkodaException('Air conditioning action failed')

   # Parking heater heating/ventilation (RS)
    async def set_pheater(self, mode, spin):
        """Set the mode for the parking heater."""
        if not self.is_pheater_heating_supported:
            _LOGGER.error('No parking heater support.')
            raise SkodaInvalidRequestException('No parking heater support.')
        if self._requests['preheater'].get('id', False):
            timestamp = self._requests.get('preheater', {}).get('timestamp', datetime.now())
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('preheater', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('A parking heater action is already in progress')
        if not mode in ['heating', 'ventilation', 'off']:
            _LOGGER.error(f'{mode} is an invalid action for parking heater')
            raise SkodaInvalidRequestException(f'{mode} is an invalid action for parking heater')
        if mode == 'off':
            data = {
                'performAction': {
                    'quickstop': {
                        'active': False
                        }
                    }
                }
        else:
            data = {
                'performAction': {
                    'quickstart': {
                        'climatisationDuration': self.pheater_duration,
                        'startMode': mode,
                        'active': True
                    }
                }
            }
        try:
            self._requests['latest'] = 'Preheater'
            _LOGGER.debug(f'Executing setPreHeater with data: {data}')
            response = await self._connection.setPreHeater(self.vin, data, spin)
            if not response:
                self._requests['preheater']['status'] = 'Failed'
                _LOGGER.error(f'Failed to set parking heater to {mode}')
                raise SkodaException(f'setPreHeater returned "{response}"')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['preheater'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('rs', response.get('id', 0))
                self._requests['preheater']['status'] = status
                self._requests['preheater'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to set parking heater mode to {mode} - {error}')
            self._requests['preheater']['status'] = 'Exception'
        raise SkodaException('Pre-heater action failed')

   # Lock (RLU)
    async def set_lock(self, action, spin):
        """Remote lock and unlock actions."""
        if not self._services.get('rlu_v1', False):
            _LOGGER.info('Remote lock/unlock is not supported.')
            raise SkodaInvalidRequestException('Remote lock/unlock is not supported.')
        if self._requests['lock'].get('id', False):
            timestamp = self._requests.get('lock', {}).get('timestamp', datetime.now() - timedelta(minutes=5))
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('lock', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('A lock action is already in progress')
        if action in ['lock', 'unlock']:
            data = '<rluAction xmlns="http://audi.de/connect/rlu">\n<action>' + action + '</action>\n</rluAction>'
        else:
            _LOGGER.error(f'Invalid lock action: {action}')
            raise SkodaInvalidRequestException(f'Invalid lock action: {action}')
        try:
            self._requests['latest'] = 'Lock'
            response = await self._connection.setLock(self.vin, data, spin)
            if not response:
                self._requests['lock']['status'] = 'Failed'
                _LOGGER.error(f'Failed to {action} vehicle')
                raise SkodaException(f'Failed to {action} vehicle')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['lock'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('rlu', response.get('id', 0))
                self._requests['lock']['status'] = status
                self._requests['lock'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to {action} vehicle - {error}')
            self._requests['lock']['status'] = 'Exception'
        raise SkodaException('Lock action failed')

   # Honk and flash (RHF)
    async def set_honkandflash(self, action, lat=None, lng=None):
        """Turn on/off honk and flash."""
        if not self._services.get('rhonk_v1', False):
            _LOGGER.info('Remote honk and flash is not supported.')
            raise SkodaInvalidRequestException('Remote honk and flash is not supported.')
        if self._requests['honkandflash'].get('id', False):
            timestamp = self._requests.get('honkandflash', {}).get('timestamp', datetime.now() - timedelta(minutes=5))
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('honkandflash', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('A honk and flash action is already in progress')
        if action == 'flash':
            operationCode = 'FLASH_ONLY'
        elif action == 'honkandflash':
            operationCode = 'HONK_AND_FLASH'
        else:
            raise SkodaInvalidRequestException(f'Invalid action "{action}", must be one of "flash" or "honkandflash"')
        try:
            # Get car position
            if lat is None:
                lat = int(self.attrs.get('findCarResponse', {}).get('Position', {}).get('carCoordinate', {}).get('latitude', None))
            if lng is None:
                lng = int(self.attrs.get('findCarResponse', {}).get('Position', {}).get('carCoordinate', {}).get('longitude', None))
            if lat is None or lng is None:
                raise SkodaConfigException('No location available, location information is needed for this action')
            data = {
                'honkAndFlashRequest': {
                    'serviceOperationCode': operationCode,
                    'userPosition': {
                        'latitude': lat,
                        'longitude': lng
                    }
                }
            }
            self._requests['latest'] = 'HonkAndFlash'
            response = await self._connection.setHonkAndFlash(self.vin, data)
            if not response:
                self._requests['honkandflash']['status'] = 'Failed'
                _LOGGER.error(f'Failed to execute honk and flash action')
                raise SkodaException(f'Failed to execute honk and flash action')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['honkandflash'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('state', 'Unknown'),
                    'id': response.get('id', 0),
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('rhf', response.get('id', 0))
                self._requests['honkandflash']['status'] = status
                self._requests['honkandflash'].pop('id', None)
                return status
        except (SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to {action} vehicle - {error}')
            self._requests['honkandflash']['status'] = 'Exception'
        raise SkodaException('Honk and flash action failed')

   # Refresh vehicle data (VSR)
    async def set_refresh(self):
        """Wake up vehicle and update status data."""
        if not self._services.get('statusreport_v1', {}).get('active', False):
           _LOGGER.info('Data refresh is not supported.')
           raise SkodaInvalidRequestException('Data refresh is not supported.')
        if self._requests['refresh'].get('id', False):
            timestamp = self._requests.get('refresh', {}).get('timestamp', datetime.now() - timedelta(minutes=5))
            expired = datetime.now() - timedelta(minutes=3)
            if expired > timestamp:
                self._requests.get('refresh', {}).pop('id')
            else:
                raise SkodaRequestInProgressException('A data refresh request is already in progress')
        try:
            self._requests['latest'] = 'Refresh'
            response = await self._connection.setRefresh(self.vin)
            if not response:
                _LOGGER.error('Failed to request vehicle update')
                self._requests['refresh']['status'] = 'Failed'
                raise SkodaException('Failed to execute data refresh')
            else:
                self._requests['remaining'] = response.get('rate_limit_remaining', -1)
                self._requests['refresh'] = {
                    'timestamp': datetime.now().replace(microsecond=0),
                    'status': response.get('status', 'Unknown'),
                    'id': response.get('id', 0)
                }
                if response.get('state', None) == 'Throttled':
                    status = 'Throttled'
                else:
                    status = await self.wait_for_request('vsr', response.get('id', 0))
                self._requests['refresh']['status'] = status
                self._requests['refresh'].pop('id', None)
                return status
        except(SkodaInvalidRequestException, SkodaException):
            raise
        except Exception as error:
            _LOGGER.warning(f'Failed to execute data refresh - {error}')
            self._requests['refresh']['status'] = 'Exception'
        raise SkodaException('Data refresh failed')

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
        """Check if access to service has expired. Return true if expired."""
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
        """Returns dashboard, creates new if none exist."""
        if self._dashboard is None:
            # Init new dashboard if none exist
            from skodaconnect.dashboard import Dashboard
            self._dashboard = Dashboard(self, **config)
        elif config != self._dashboard._config:
            # Init new dashboard on config change
            from skodaconnect.dashboard import Dashboard
            self._dashboard = Dashboard(self, **config)
        return self._dashboard

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
        for car in self.attrs.get('realCars', []):
            if self.vin == car.get('vehicleIdentificationNumber', ''):
                return car.get('nickname', None)

    @property
    def is_nickname_supported(self):
        for car in self.attrs.get('realCars', []):
            if self.vin == car.get('vehicleIdentificationNumber', ''):
                if car.get('nickname', False):
                    return True

    @property
    def deactivated(self):
        for car in self.attrs.get('realCars', []):
            if self.vin == car.get('vehicleIdentificationNumber', ''):
                return car.get('deactivated', False)

    @property
    def is_deactivated_supported(self):
        for car in self.attrs.get('realCars', []):
            if self.vin == car.get('vehicleIdentificationNumber', ''):
                if car.get('deactivated', False):
                    return True

    @property
    def model(self):
        """Return model"""
        if self._specification.get('trimLevel', False):
            model = self._specification.get('title', 'Unknown') + ' ' + self._specification.get('trimLevel', '')
            return model
        return self._specification.get('title', 'Unknown')

    @property
    def is_model_supported(self):
        """Return true if model is supported."""
        if self._specification.get('title', False):
            return True

    @property
    def model_year(self):
        """Return model year"""
        return self._specification.get('manufacturingDate', 'Unknown')

    @property
    def is_model_year_supported(self):
        """Return true if model year is supported."""
        if self._specification.get('manufacturingDate', False):
            return True

    @property
    def model_image_small(self):
        """Return URL for model image"""
        return self._modelimages

    @property
    def is_model_image_small_supported(self):
        """Return true if model image url is not None."""
        if self._modelimages is not None:
            return True

    @property
    def model_image_large(self):
        """Return URL for model image"""
        return self._modelimagel

    @property
    def is_model_image_large_supported(self):
        """Return true if model image url is not None."""
        if self._modelimagel is not None:
            return True

    # Battery
    @property
    def battery_capacity(self):
        value = -1
        if 'capacityInKWh' in self._specification.get('battery', {}):
            value = self._specification.get('battery', {}).get('capacityInKWh', 0)
        return int(value)

    @property
    def is_battery_capacity_supported(self):
        if 'capacityInKWh' in self._specification.get('battery', {}):
            return True
        return False

    @property
    def max_charging_power(self):
        value = -1
        if 'maxChargingPowerInKW' in self._specification:
            value = self._specification.get('maxChargingPowerInKW', 0)
        return int(value)

    @property
    def is_max_charging_power_supported(self):
        if 'maxChargingPowerInKW' in self._specification:
            return True
        return False

    # Engine
    @property
    def engine_power(self):
        value = -1
        if 'powerInKW' in self._specification.get('engine', {}):
            value = self._specification.get('engine', {}).get('powerInKW', 0)
        return int(value)

    @property
    def is_engine_power_supported(self):
        if 'powerInKW' in self._specification.get('engine', {}):
            return True
        return False

    @property
    def engine_type(self):
        value = ''
        if 'type' in self._specification.get('engine', {}):
            value = self._specification.get('engine', {}).get('type', '')
        return value

    @property
    def is_engine_type_supported(self):
        if 'type' in self._specification.get('engine', {}):
            return True
        return False

    @property
    def engine_capacity(self):
        value = ''
        if 'capacityInLiters' in self._specification.get('engine', {}):
            value = self._specification.get('engine', {}).get('capacityInLiters', '')
        return value

    @property
    def is_engine_capacity_supported(self):
        if 'capacityInLiters' in self._specification.get('engine', {}):
            return True
        return False

  # Lights
    @property
    def parking_light(self):
        """Return true if parking light is on"""
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301010001'].get('value', 0))
            return True if response != 2 else False
        if self.attrs.get('vehicle_remote', {}):
            return True if self.attrs.get('vehicle_remote', {}).get('lights', {}).get('overallStatus', 0) != 'OFF' else False

    @property
    def is_parking_light_supported(self):
        """Return true if parking light is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301010001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False
        if self.attrs.get('vehicle_remote', {}):
            if 'overallStatus' in self.attrs.get('vehicle_remote', {}).get('lights', {}):
                return True
            else:
                False

  # Connection status
    @property
    def last_connected(self):
        """Return when vehicle was last connected to connect servers."""
        last_connected_utc = None
        if self.attrs.get('StoredVehicleDataResponse', False):
            last_connected_utc = self.attrs.get('StoredVehicleDataResponse').get('vehicleData').get('data')[0].get('field')[0].get('tsCarSentUtc')
            if isinstance(last_connected_utc, datetime):
                last_connected = last_connected_utc.astimezone().replace(tzinfo=None)
            else:
                last_connected = datetime.strptime(last_connected_utc,'%Y-%m-%dT%H:%M:%SZ').astimezone().replace(tzinfo=None)
        elif self.attrs.get('vehicle_remote', False):
            last_connected_utc = self.attrs.get('vehicle_remote', {}).get('capturedAt', None)
            if isinstance(last_connected_utc, datetime):
                last_connected = last_connected_utc.astimezone().replace(tzinfo=None)
            else:
                last_connected = datetime.strptime(last_connected_utc,'%Y-%m-%dT%H:%M:%S.%fZ').astimezone().replace(tzinfo=None).replace(microsecond=0)
        return last_connected.isoformat()

    @property
    def is_last_connected_supported(self):
        """Return when vehicle was last connected to connect servers."""
        if self.attrs.get('StoredVehicleDataResponse', False):
            if next(iter(next(iter(self.attrs.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})), None).get('field', {})), None).get('tsCarSentUtc', []):
                return True
        elif self.attrs.get('vehicle_remote', {}).get('capturedAt', False):
            return True

  # Service information
    @property
    def distance(self):
        """Return vehicle odometer."""
        if self.attrs.get('vehicle_status', False):
            value = self.attrs.get('vehicle_status').get('totalMileage', 0)
        elif self.attrs.get('vehicle_remote', False):
            value = self.attrs.get('vehicle_remote').get('mileageInKm', 0)
        else:
            value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0101010002'].get('value', 0)
        if value:
            return int(value)

    @property
    def is_distance_supported(self):
        """Return true if odometer is supported"""
        if self.attrs.get('vehicle_status', False):
            if 'totalMileage' in self.attrs.get('vehicle_status', {}):
                return True
        elif self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0101010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
        elif self.attrs.get('vehicle_remote', False):
            if 'mileageInKm' in self.attrs.get('vehicle_remote', {}):
                return True
        return False

    @property
    def service_inspection(self):
        """Return time left until service inspection"""
        value = -1
        if self.attrs.get('vehicle_status', {}).get('nextInspectionTime', False):
            value = self.attrs.get('vehicle_status', {}).get('nextInspectionTime', 0)
        elif self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010004',{}).get('value', False):
            value = 0-int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010004',{}).get('value', 0))
        return int(value)

    @property
    def is_service_inspection_supported(self):
        if self.attrs.get('vehicle_status', False):
            if 'nextInspectionTime' in self.attrs.get('vehicle_status', {}):
                return True
        elif self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010004' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if self.attrs.get('StoredVehicleDataResponseParsed').get('0x0203010004').get('value', None) is not None:
                    return True
        return False

    @property
    def service_inspection_distance(self):
        """Return time left until service inspection"""
        value = -1
        if self.attrs.get('vehicle_status', {}).get('nextInspectionDistance', False):
            value = self.attrs.get('vehicle_status', {}).get('nextInspectionDistance', 0)
        elif self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010003',{}).get('value', False):
            value = 0-int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010003',{}).get('value', 0))
        return int(value)

    @property
    def is_service_inspection_distance_supported(self):
        if self.attrs.get('vehicle_status', False):
            if 'nextInspectionDistance' in self.attrs.get('vehicle_status', {}):
                return True
        elif self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010003' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if self.attrs.get('StoredVehicleDataResponseParsed').get('0x0203010003').get('value', None) is not None:
                    return True
        return False

    @property
    def oil_inspection(self):
        """Return time left until oil inspection"""
        value = -1
        if self.attrs.get('vehicle_status', {}).get('nextOilServiceTime', False):
            value = self.attrs.get('vehicle_status', {}).get('nextOilServiceTime', 0)
        elif self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010002', {}).get('value', False):
            value = 0-int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010002',{}).get('value', 0))
        return int(value)

    @property
    def is_oil_inspection_supported(self):
        if self.attrs.get('vehicle_status', False):
            if 'nextOilServiceTime' in self.attrs.get('vehicle_status', {}):
                return True
        elif self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0203010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if self.attrs.get('StoredVehicleDataResponseParsed').get('0x0203010002').get('value', None) is not None:
                    return True
        return False

    @property
    def oil_inspection_distance(self):
        """Return distance left until oil inspection"""
        value = -1
        if self.attrs.get('vehicle_status', {}).get('nextOilServiceDistance', False):
            value = self.attrs.get('vehicle_status', {}).get('nextOilServiceDistance', 0)
        elif self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010001', {}).get('value', False):
            value = 0-int(self.attrs.get('StoredVehicleDataResponseParsed', {}).get('0x0203010001',{}).get('value', 0))
        return int(value)

    @property
    def is_oil_inspection_distance_supported(self):
        if self.attrs.get('vehicle_status', False):
            if 'nextOilServiceDistance' in self.attrs.get('vehicle_status', {}):
                return True
        elif self.attrs.get('StoredVehicleDataResponseParsed', False):
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
        if self.attrs.get('charger', False):
            cstate = self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('chargingState', {}).get('content', '')
        elif self.attrs.get('charging', False):
            cstate = self.attrs.get('charging', {}).get('state', '')
        return 1 if cstate in ['charging', 'Charging'] else 0

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
    def min_charge_level(self):
        """Return the charge level that car charges directly to"""
        if self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerBasicSetting', {}).get('chargeMinLimit', False):
            return self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerBasicSetting', {}).get('chargeMinLimit', 0)
        elif self.attrs.get('chargerSettings', False):
            return self.attrs.get('chargerSettings', {}).get('targetStateOfChargeInPercent', 0)
        else:
            return 0

    @property
    def is_min_charge_level_supported(self):
        """Return true if car supports setting the min charge level"""
        if self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerBasicSetting', {}).get('chargeMinLimit', False):
            return True
        elif self.attrs.get('chargerSettings', {}).get('targetStateOfChargeInPercent', False):
            return True
        return False

    @property
    def plug_autounlock(self):
        """Return the state of plug auto unlock at charged"""
        if self.attrs.get('chargerSettings', False):
            return self.attrs.get('chargerSettings', {}).get('autoUnlockPlugWhenCharged', 0)
        else:
            return 0

    @property
    def is_plug_autounlock_supported(self):
        """Return true if plug auto unlock is supported"""
        if self.attrs.get('chargerSettings', {}).get('autoUnlockPlugWhenCharged', False):
            return True
        return False

    @property
    def battery_level(self):
        """Return battery level"""
        if self.attrs.get('charger', False):
            return int(self.attrs.get('charger').get('status', {}).get('batteryStatusData', {}).get('stateOfCharge', {}).get('content', 0))
        elif self.attrs.get('battery', False):
            return int(self.attrs.get('battery').get('stateOfChargeInPercent', 0))
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
        if self.attrs.get('charger', False):
            value = int(self.attrs.get('charger').get('settings').get('maxChargeCurrent').get('content'))
            if value == 254:
                return "Maximum"
            if value == 252:
                return "Reduced"
            if value == 0:
                return "Unknown"
            else:
                return value
        elif self.attrs.get('chargerSettings', False):
            value = self.attrs.get('chargerSettings', {}).get('maxChargeCurrentAc', 'Unknown')
            return value
        return 0

    @property
    def is_charge_max_ampere_supported(self):
        """Return true if Charger Max Ampere is supported"""
        if self.attrs.get('charger', False):
            if 'settings' in self.attrs.get('charger', {}):
                if 'maxChargeCurrent' in self.attrs.get('charger', {})['settings']:
                    return True
        elif self.attrs.get('chargerSettings', False):
            if self.attrs.get('chargerSettings', {}).get('maxChargeCurrentAc', False):
                return True
        return False

    @property
    def charging_cable_locked(self):
        """Return plug locked state"""
        response = ''
        if self.attrs.get('charger', False):
            response = self.attrs.get('charger')['status']['plugStatusData']['lockState'].get('content', 0)
        elif self.attrs.get('plug', False):
            response = self.attrs.get('plug', {}).get('lockState', 0)
        return True if response in ['Locked', 'locked'] else False

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
        response = ''
        if self.attrs.get('charger', False):
            response = self.attrs.get('charger', {}).get('status', {}).get('plugStatusData').get('plugState', {}).get('content', 0)
        elif self.attrs.get('plug', False):
            response = self.attrs.get('plug', {}).get('connectionState', 0)
        return True if response in ['Connected', 'connected'] else False

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
        """Return minutes to charging complete"""
        if self.external_power:
            if self.attrs.get('charging', {}).get('remainingToCompleteInSeconds', False):
                minutes = int(self.attrs.get('charging', {}).get('remainingToCompleteInSeconds', 0))/60
            elif self.attrs.get('charger', {}).get('status', {}).get('batteryStatusData', {}).get('remainingChargingTime', False):
                minutes = self.attrs.get('charger', {}).get('status', {}).get('batteryStatusData', {}).get('remainingChargingTime', {}).get('content', 0)
            try:
                if minutes == -1: return '00:00'
                if minutes == 65535: return '00:00'
                return "%02d:%02d" % divmod(minutes, 60)
            except Exception:
                pass
        return '00:00'

    @property
    def is_charging_time_left_supported(self):
        """Return true if charging is supported"""
        return self.is_charging_supported

    @property
    def charging_power(self):
        """Return charging power in watts."""
        if self.attrs.get('charging', False):
            return int(self.attrs.get('charging', {}).get('chargingPowerInWatts', 0))
        else:
            return 0

    @property
    def is_charging_power_supported(self):
        """Return true if charging power is supported."""
        if self.attrs.get('charging', False):
            if self.attrs.get('charging', {}).get('chargingPowerInWatts', False) is not False:
                return True
        return False

    @property
    def charge_rate(self):
        """Return charge rate in km per h."""
        if self.attrs.get('charging', False):
            return int(self.attrs.get('charging', {}).get('chargingRateInKilometersPerHour', 0))
        else:
            return 0

    @property
    def is_charge_rate_supported(self):
        """Return true if charge rate is supported."""
        if self.attrs.get('charging', False):
            if self.attrs.get('charging', {}).get('chargingRateInKilometersPerHour', False) is not False:
                return True
        return False

    @property
    def external_power(self):
        """Return true if external power is connected."""
        response = ''
        if self.attrs.get('charger', False):
            response = self.attrs.get('charger', {}).get('status', {}).get('chargingStatusData', {}).get('externalPowerSupplyState', {}).get('content', 0)
        elif self.attrs.get('charging', False):
            response = self.attrs.get('charging', {}).get('chargingType', 'Invalid')
            response = 'Charging' if self.attrs.get('charging', {}).get('chargingType', 'Invalid') != 'Invalid' else 'Invalid'
        return True if response in ['stationConnected', 'available', 'Charging'] else False

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
                if self._services.get('carfinder_v1', {}).get('active', False):
                    lat = int(posObj.get('Position').get('carCoordinate').get('latitude'))/1000000
                    lng = int(posObj.get('Position').get('carCoordinate').get('longitude'))/1000000
                    parkingTime = posObj.get('parkingTimeUTC')
                elif self._services.get('PARKING_POSITION', {}).get('active', False):
                    lat = posObj.get('latitude')
                    lng = posObj.get('longitude')
                    parkingTime = posObj.get('lastUpdatedAt')

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
            return True
        elif self._services.get('PARKING_POSITION', {}).get('active', False):
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
        if isinstance(parkTime_utc, datetime):
            parkTime = parkTime_utc.astimezone().replace(tzinfo=None)
        else:
            parkTime = datetime.strptime(parkTime_utc,'%Y-%m-%dT%H:%M:%SZ').astimezone().replace(tzinfo=None)
        return parkTime.isoformat()

    @property
    def is_parking_time_supported(self):
        """Return true if vehicle parking timestamp is supported."""
        if 'parkingTimeUTC' in self.attrs.get('findCarResponse', {}):
            return True

   # Vehicle fuel level and range
    @property
    def primary_range(self):
        value = -1
        if '0x0301030006' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030006']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030006'].get('value', 0)
        return int(value)

    @property
    def is_primary_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030006' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030006']:
                    return True
        return False

    @property
    def primary_drive(self):
        value = -1
        if '0x0301030007' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030007']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030007'].get('value', 0)
        return int(value)

    @property
    def is_primary_drive_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030007' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030007']:
                    return True
        return False

    @property
    def secondary_range(self):
        value = -1
        if '0x0301030008' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008'].get('value', 0)
        return int(value)

    @property
    def is_secondary_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030008' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030008']:
                    return True
        return False

    @property
    def secondary_drive(self):
        value = -1
        if '0x0301030009' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030009']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030009'].get('value', 0)
        return int(value)

    @property
    def is_secondary_drive_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301030009' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030009']:
                    return True
        return False

    @property
    def electric_range(self):
        value = -1
        if self.is_secondary_drive_supported:
            if self.secondary_drive == 3:
                value = self.secondary_range
        elif self.is_primary_drive_supported:
            if self.primary_drive == 3:
                value = self.primary_range
        elif self.attrs.get('battery', False):
            value = int(self.attrs.get('battery', {}).get('cruisingRangeElectricInMeters', 0))/1000
        return int(value)

    @property
    def is_electric_range_supported(self):
        if self.is_secondary_drive_supported:
            if self.secondary_drive == 3:
                return self.is_secondary_range_supported
        elif self.is_primary_drive_supported:
            if self.primary_drive == 3:
                return self.is_primary_range_supported
        elif self.attrs.get('battery', False):
            if 'cruisingRangeElectricInMeters' in self.attrs.get('battery'):
                return True
        return False

    @property
    def combustion_range(self):
        value = -1
        if self.is_primary_drive_supported:
            if not self.primary_drive == 3:
                return self.primary_range
        elif self.is_secondary_drive_supported:
            if not self.secondary_drive == 3:
                return self.secondary_range
        return -1

    @property
    def is_combustion_range_supported(self):
        if self.is_primary_drive_supported:
            if not self.primary_drive == 3:
                return self.is_primary_range_supported
        elif self.is_secondary_drive_supported:
            if not self.secondary_drive == 3:
                return self.is_secondary_range_supported
        return False

    @property
    def combined_range(self):
        if self.is_combustion_range_supported and self.is_electric_range_supported:
            return self.combustion_range + self.electric_range
        return -1


    @property
    def is_combined_range_supported(self):
        if self.is_combustion_range_supported and self.is_electric_range_supported:
            return True
        return False

    @property
    def fuel_level(self):
        value = -1
        if self.attrs.get('vehicle_status', False):
            value = round(100 * self.attrs.get('vehicle_status', {}).get('primaryFuelLevel', 0))
        elif '0x030103000A' in self.attrs.get('StoredVehicleDataResponseParsed'):
            if 'value' in self.attrs.get('StoredVehicleDataResponseParsed')['0x030103000A']:
                value = self.attrs.get('StoredVehicleDataResponseParsed')['0x030103000A'].get('value', 0)
        return int(value)

    @property
    def is_fuel_level_supported(self):
        if self.attrs.get('vehicle_status', False):
            if self.attrs.get('vehicle_status', {}).get('primaryFuelLevel', False):
                return True
        elif self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030103000A' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
        return False

  # Climatisation settings
    @property
    def climatisation_target_temperature(self):
        """Return the target temperature from climater."""
        if self.attrs.get('climater', False):
            value = self.attrs.get('climater').get('settings', {}).get('targetTemperature', {}).get('content', 2730)
        elif self.attrs.get('airConditioningSettings', False):
            value = float(self.attrs.get('airConditioningSettings').get('targetTemperatureInKelvin', 273.15)-0.15)*10
        if value:
            reply = float((value / 10) - 273)
            return reply

    @property
    def is_climatisation_target_temperature_supported(self):
        """Return true if climatisation target temperature is supported."""
        if self.attrs.get('climater', False):
            if 'settings' in self.attrs.get('climater', {}):
                if 'targetTemperature' in self.attrs.get('climater', {})['settings']:
                    return True
        elif self.attrs.get('airConditioningSettings', False):
            if 'targetTemperatureInKelvin' in self.attrs.get('airConditioningSettings', {}):
                return True
        return False

    @property
    def climatisation_time_left(self):
        """Return time left for climatisation in hours:minutes."""
        if self.attrs.get('airConditioning', {}).get('remainingTimeToReachTargetTemperatureInSeconds', False):
            try:
                minutes = int(self.attrs.get('airConditioning', {}).get('remainingTimeToReachTargetTemperatureInSeconds', 0))/60
                if not 0 <= minutes <= 65535:
                    return "00:00"
                return "%02d:%02d" % divmod(minutes, 60)
            except Exception:
                pass
        return "00:00"

    @property
    def is_climatisation_time_left_supported(self):
        #"""Return true if remainingTimeToReachTargetTemperatureInSeconds is supported."""
        """ Return true if airConditioning is supported. """
        #if self.attrs.get('airConditioning', {}).get('remainingTimeToReachTargetTemperatureInSeconds', False):
        if self.attrs.get('airConditioning', False):
            return True
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
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301020001'].get('value', 0))
        if response:
            return round(float((response / 10) - 273.15), 1)
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
    def electric_climatisation_attributes(self):
        """Return climatisation attributes."""
        data = {}
        if self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', False):
            data['source'] = self.attrs.get('climater', {}).get('settings', {}).get('heaterSource', {}).get('content', '')
            data['status'] = self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', '')
        elif self.attrs.get('airConditioning', False):
            data['status'] = self.attrs.get('airConditioning', {}).get('state', '')
        return data

    @property
    def is_electric_climatisation_attributes_supported(self):
        """Return true if vehichle has climater."""
        return self.is_climatisation_supported

    @property
    def electric_climatisation(self):
        """Return status of climatisation."""
        if self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', False):
            climatisation_type = self.attrs.get('climater', {}).get('settings', {}).get('heaterSource', {}).get('content', '')
            status = self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', '')
            if status in ['heating', 'cooling', 'ventilation', 'on'] and climatisation_type == 'electric':
                return True
        elif self.attrs.get('airConditioning', {}).get('state', 'off').lower() in ['on', 'heating', 'cooling', 'ventilation']:
            return True
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
        if status in ['heating', 'cooling', 'ventilation', 'heatingAuxiliary', 'on'] and climatisation_type == 'auxiliary':
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
        if self.attrs.get('climater', {}).get('status', {}).get('climatisationStatusData', {}).get('climatisationState', {}).get('content', False):
            return True
        elif self.attrs.get('airConditioning', {}).get('state', False):
            return True
        return False

    @property
    def aircon_at_unlock(self):
        """Return status of air-conditioning at unlock setting."""
        return self.attrs.get('airConditioningSettings', {}).get('airConditioningAtUnlock', False)

    @property
    def is_aircon_at_unlock_supported(self):
        """Return true if air-conditioning at unlock is supported."""
        if self.attrs.get('airConditioningSettings', {}).get('airConditioningAtUnlock', False):
            return True
        return False

    @property
    def window_heater_new(self):
        """Return status of window heater."""
        status_front = status_rear = ''
        if self.attrs.get('airConditioning', {}).get('windowsHeatingStatuses', False):
            status = self.attrs.get('airConditioning', {}).get('windowsHeatingStatuses', {})
            for sub_status in status:
                if (sub_status.get('windowLocation')=='Front'):
                    status_front = sub_status.get('state')
                if (sub_status.get('windowLocation')=='Rear'):
                    status_rear = sub_status.get('state')
        if status_front.lower() == 'on':
            return True
        if status_rear.lower() == 'on':
            return True
        #if self.attrs.get('airConditioningSettings', {}).get('windowsHeatingEnabled', False):
        #    return self.attrs.get('airConditioningSettings', {}).get('windowsHeatingEnabled', False)
        return False

    @property
    def is_window_heater_new_supported(self):
        """Return true if vehichle has heater."""
        if self.is_electric_climatisation_supported:
            if self.attrs.get('airConditioning', {}).get('windowsHeatingStatuses', False):
                return True
            #elif self.attrs.get('airConditioningSettings', {}).get('windowsHeatingEnabled', False):
            #    return True
        return False

    @property
    def climatisation_window_heat(self):
        """Return window heat during climatisation setting."""
        return self.attrs.get('airConditioningSettings', {}).get('windowHeatingEnabled', False)

    @property
    def is_climatisation_window_heat_supported(self):
        """Return true if window heat during climatisation is available."""
        if self.attrs.get('airConditioningSettings', {}).get('windowHeatingEnabled', {}):
            return True
        return False

    @property
    def window_heater(self):
        """Return status of window heater."""
        status_front = status_rear = ''
        if self.attrs.get('climater', False):
            status_front = self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateFront', {}).get('content', '')
            status_rear = self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateRear', {}).get('content', '')
        if status_front in ['on', 'On', 'ON']:
            return True
        if status_rear in ['on', 'On', 'ON']:
            return True
        return False

    @property
    def is_window_heater_supported(self):
        """Return true if vehichle has heater."""
        if self.is_electric_climatisation_supported:
            if self.attrs.get('climater', False):
                if self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateFront', {}).get('content', '') in ['on', 'off']:
                    return True
                if self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateRear', {}).get('content', '') in ['on', 'off']:
                    return True
        return False

    @property
    def window_heater_attributes(self):
        """Return window heater attributes."""
        data = {}
        if self.attrs.get('climater', False):
            data['windowHeatingStateFront'] = self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateFront', {}).get('content', '')
            data['windowHeatingStateRear']  = self.attrs.get('climater', {}).get('status', {}).get('windowHeatingStatusData', {}).get('windowHeatingStateRear', {}).get('content', '')
        elif self.attrs.get('airConditioning', False):
            if self.attrs.get('airConditioning', {}).get('windowsHeatingStatuses', False):
            # return self.attrs.get('airConditioningSettings', {}).get('windowsHeatingEnabled', False)
                statuses = self.attrs.get('airConditioning', {}).get('windowsHeatingStatuses', {})
                for status in statuses:
                    data[status.get('windowLocation', '?')] = status.get('state','N/A')
        return data

    @property
    def is_window_heater_attributes_supported(self):
        """Return true if vehichle has a window heater."""
        return self.is_window_heater_supported

    @property
    def seat_heating_front_left(self):
        """Return status of seat heating front left."""
        return self.attrs.get('airConditioningSettings', {}).get('zonesSettings', {}).get('frontLeftEnabled', False)

    @property
    def is_seat_heating_front_left_supported(self):
        """Return true if vehichle has seat heating front left."""
        if self.attrs.get('airConditioning', {}).get('seatHeatingSupport', {}).get('frontLeftAvailable', False):
            return True
        return False

    @property
    def seat_heating_front_right(self):
        """Return status of seat heating front right."""
        return self.attrs.get('airConditioningSettings', {}).get('zonesSettings', {}).get('frontRightEnabled', False)

    @property
    def is_seat_heating_front_right_supported(self):
        """Return true if vehichle has seat heating front right."""
        if self.attrs.get('airConditioning', {}).get('seatHeatingSupport', {}).get('frontRightAvailable', False):
            return True
        return False

    @property
    def seat_heating_rear_left(self):
        """Return status of seat heating rear left."""
        return self.attrs.get('airConditioningSettings', {}).get('zonesSettings', {}).get('rearLeftEnabled', False)

    @property
    def is_seat_heating_rear_left_supported(self):
        """Return true if vehichle has seat heating rear left."""
        if self.attrs.get('airConditioning', {}).get('seatHeatingSupport', {}).get('rearLeftAvailable', False):
            return True
        return False

    @property
    def seat_heating_rear_right(self):
        """Return status of seat heating rear right."""
        return self.attrs.get('airConditioningSettings', {}).get('zonesSettings', {}).get('rearRightEnabled', False)

    @property
    def is_seat_heating_rear_right_supported(self):
        """Return true if vehichle has seat heating rear right."""
        if self.attrs.get('airConditioning', {}).get('seatHeatingSupport', {}).get('rearRightAvailable', False):
            return True
        return False

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
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301050001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050001'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            return True

    @property
    def window_closed_left_front(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050001'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'FRONT_LEFT')
            return True if window.get('status', 'UNSUPPORTED') == 'CLOSED' else False

    @property
    def is_window_closed_left_front_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301050001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050001'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'FRONT_LEFT')
            return True if window.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def window_closed_right_front(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050005'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'FRONT_RIGHT')
            return True if window.get('status', 'UNSUPPORTED') == 'CLOSED' else False

    @property
    def is_window_closed_right_front_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301050005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050005'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'FRONT_RIGHT')
            return True if window.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def window_closed_left_back(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050003'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'REAR_LEFT')
            return True if window.get('status', 'UNSUPPORTED') == 'CLOSED' else False

    @property
    def is_window_closed_left_back_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301050003' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050003'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'REAR_LEFT')
            return True if window.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def window_closed_right_back(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050007'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'REAR_RIGHT')
            return True if window.get('status', 'UNSUPPORTED') == 'CLOSED' else False

    @property
    def is_window_closed_right_back_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301050007' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050007'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'REAR_RIGHT')
            return True if window.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def sunroof_closed(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030105000B'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            window = next(item for item in windows if item['name'] == 'SUN_ROOF')
            return True if window.get('status', 'UNSUPPORTED') == 'CLOSED' else False

    @property
    def is_sunroof_closed_supported(self):
        """Return true if sunroof state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030105000B' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030105000B'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('windows', {}):
            windows = self.attrs.get('vehicle_remote', {}).get('windows', {})
            sunroof = next(item for item in windows if item['name'] == 'SUN_ROOF')
            return True if sunroof.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False


  # Locks
    @property
    def door_locked(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            # LEFT FRONT
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040001'].get('value', 0))
            if response != 2:
                return False
            # LEFT REAR
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040004'].get('value', 0))
            if response != 2:
                return False
            # RIGHT FRONT
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040007'].get('value', 0))
            if response != 2:
                return False
            # RIGHT REAR
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000A'].get('value', 0))
            if response != 2:
                return False
            return True
        elif self.attrs.get('vehicle_remote', {}).get('status', {}):
            response = self.attrs.get('vehicle_remote', {}).get('status', {}).get('locked', 0)
            return True if response == 'YES' else False

    @property
    def is_door_locked_supported(self):
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301040001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040001'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('status', {}):
            response = self.attrs.get('vehicle_remote', {}).get('status', {}).get('locked', 0)
            return True if response in ['YES', 'NO'] else False
        return False

    @property
    def trunk_locked(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000D'].get('value', 0))
        if response == 2:
            return True
        else:
            return False

    @property
    def is_trunk_locked_supported(self):
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030104000D' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000D'].get('value', 0))
        return True if response != 0 else False

  # Doors, hood and trunk
    @property
    def hood_closed(self):
        """Return true if hood is closed"""
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040011'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', [])
            bonnet = next(item for item in doors if item['name'] == 'BONNET')
            return True if bonnet.get('status', 'UNSUPPORTED') in ['CLOSED', 'LOCKED'] else False

    @property
    def is_hood_closed_supported(self):
        """Return true if hood state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301040011' in self.attrs.get('StoredVehicleDataResponseParsed', {}):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040011'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', False):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', [])
            bonnet = next(item for item in doors if item['name'] == 'BONNET')
            return True if bonnet.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def door_closed_left_front(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040002'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'FRONT_LEFT')
            return True if door.get('status', 'UNSUPPORTED') in ['CLOSED', 'LOCKED'] else False

    @property
    def is_door_closed_left_front_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301040002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040002'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'FRONT_LEFT')
            return True if door.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def door_closed_right_front(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040008'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'FRONT_RIGHT')
            return True if door.get('status', 'UNSUPPORTED') in ['CLOSED', 'LOCKED'] else False

    @property
    def is_door_closed_right_front_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301040008' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040008'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'FRONT_RIGHT')
            return True if door.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def door_closed_left_back(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040005'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'REAR_LEFT')
            return True if door.get('status', 'UNSUPPORTED') in ['CLOSED', 'LOCKED'] else False

    @property
    def is_door_closed_left_back_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x0301040005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040005'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'REAR_LEFT')
            return True if door.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def door_closed_right_back(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000B'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'REAR_RIGHT')
            return True if door.get('status', 'UNSUPPORTED') in ['CLOSED', 'LOCKED'] else False

    @property
    def is_door_closed_right_back_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030104000B' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000B'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'REAR_RIGHT')
            return True if door.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False

    @property
    def trunk_closed(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000E'].get('value', 0))
            return True if response == 3 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'TRUNK')
            return True if door.get('status', 'UNSUPPORTED') in ['CLOSED', 'LOCKED'] else False

    @property
    def is_trunk_closed_supported(self):
        """Return true if window state is supported"""
        response = 0
        if self.attrs.get('StoredVehicleDataResponseParsed', False):
            if '0x030104000E' in self.attrs.get('StoredVehicleDataResponseParsed'):
                response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000E'].get('value', 0))
            return True if response != 0 else False
        elif self.attrs.get('vehicle_remote', {}).get('doors', {}):
            doors = self.attrs.get('vehicle_remote', {}).get('doors', {})
            door = next(item for item in doors if item['name'] == 'TRUNK')
            return True if door.get('status', 'UNSUPPORTED') != 'UNSUPPORTED' else False


  # Departure timers
   # Under development
    @property
    def departure1(self):
        """Return timer status and attributes."""
        if self.attrs.get('departuretimer', False):
            try:
                data = {}
                timerdata = self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])
                profiledata = self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])
                timer = timerdata[0]
                profile = profiledata[0]
                timer.pop('timestamp', None)
                timer.pop('timerID', None)
                timer.pop('profileID', None)
                profile.pop('timestamp', None)
                profile.pop('profileName', None)
                profile.pop('profileID', None)
                data.update(timer)
                data.update(profile)
                return data
            except:
                pass
        elif self.attrs.get('timers', False):
            try:
                response = self.attrs.get('timers', [])
                if len(self.attrs.get('timers', [])) >= 1:
                    timer = response[0]
                    timer.pop('id', None)
                else:
                    timer = {}
                return timer
            except:
                pass
        return None

    @property
    def is_departure1_supported(self):
        """Return true if timer 1 is supported."""
        if len(self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])) >=1:
            return True
        elif len(self.attrs.get('timers', [])) >= 1:
            return True
        return False

    @property
    def departure2(self):
        """Return timer status and attributes."""
        if self.attrs.get('departuretimer', False):
            try:
                data = {}
                timerdata = self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])
                profiledata = self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])
                timer = timerdata[1]
                profile = profiledata[1]
                timer.pop('timestamp', None)
                timer.pop('timerID', None)
                timer.pop('profileID', None)
                profile.pop('timestamp', None)
                profile.pop('profileName', None)
                profile.pop('profileID', None)
                data.update(timer)
                data.update(profile)
                return data
            except:
                pass
        elif self.attrs.get('timers', False):
            try:
                response = self.attrs.get('timers', [])
                if len(self.attrs.get('timers', [])) >= 2:
                    timer = response[1]
                    timer.pop('id', None)
                else:
                    timer = {}
                return timer
            except:
                pass
        return None

    @property
    def is_departure2_supported(self):
        """Return true if timer 2 is supported."""
        if len(self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])) >= 2:
            return True
        elif len(self.attrs.get('timers', [])) >= 2:
            return True
        return False

    @property
    def departure3(self):
        """Return timer status and attributes."""
        if self.attrs.get('departuretimer', False):
            try:
                data = {}
                timerdata = self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])
                profiledata = self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerProfileList', {}).get('timerProfile', [])
                timer = timerdata[2]
                profile = profiledata[2]
                timer.pop('timestamp', None)
                timer.pop('timerID', None)
                timer.pop('profileID', None)
                profile.pop('timestamp', None)
                profile.pop('profileName', None)
                profile.pop('profileID', None)
                data.update(timer)
                data.update(profile)
                return data
            except:
                pass
        elif self.attrs.get('timers', False):
            try:
                response = self.attrs.get('timers', [])
                if len(self.attrs.get('timers', [])) >= 3:
                    timer = response[2]
                    timer.pop('id', None)
                else:
                    timer = {}
                return timer
            except:
                pass
        return None

    @property
    def is_departure3_supported(self):
        """Return true if timer 3 is supported."""
        if len(self.attrs.get('departuretimer', {}).get('timersAndProfiles', {}).get('timerList', {}).get('timer', [])) >= 3:
            return True
        elif len(self.attrs.get('timers', [])) >= 3:
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
        return int(self.trip_last_entry.get('averageFuelConsumption')) / 10

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
    def trip_last_average_aux_consumer_consumption(self):
        value = self.trip_last_entry.get('averageAuxConsumerConsumption')
        return float(value / 10)

    @property
    def is_trip_last_average_aux_consumer_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageAuxConsumerConsumption', None)) in (float, int):
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
        # Not implemented
        return self.trip_last_entry.get('recuperation')

    @property
    def is_trip_last_recuperation_supported(self):
        # Not implemented
        response = self.trip_last_entry
        if response and type(response.get('recuperation', None)) in (float, int):
            return True

    @property
    def trip_last_average_recuperation(self):
        value = self.trip_last_entry.get('averageRecuperation')
        return float(value / 10)

    @property
    def is_trip_last_average_recuperation_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageRecuperation', None)) in (float, int):
            return True

    @property
    def trip_last_total_electric_consumption(self):
        # Not implemented
        return self.trip_last_entry.get('totalElectricConsumption')

    @property
    def is_trip_last_total_electric_consumption_supported(self):
        # Not implemented
        response = self.trip_last_entry
        if response and type(response.get('totalElectricConsumption', None)) in (float, int):
            return True

  # Status of set data requests
    @property
    def refresh_action_status(self):
        """Return latest status of data refresh request."""
        return self._requests.get('refresh', {}).get('status', 'None')

    @property
    def refresh_action_timestamp(self):
        """Return timestamp of latest data refresh request."""
        timestamp = self._requests.get('refresh', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def charger_action_status(self):
        """Return latest status of charger request."""
        return self._requests.get('batterycharge', {}).get('status', 'None')

    @property
    def charger_action_timestamp(self):
        """Return timestamp of latest charger request."""
        timestamp = self._requests.get('charger', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def aircon_action_status(self):
        """Return latest status of air-conditioning request."""
        return self._requests.get('air-conditioning', {}).get('status', 'None')

    @property
    def aircon_action_timestamp(self):
        """Return timestamp of latest air-conditioning request."""
        timestamp = self._requests.get('air-conditioning', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def climater_action_status(self):
        """Return latest status of climater request."""
        return self._requests.get('climatisation', {}).get('status', 'None')

    @property
    def climater_action_timestamp(self):
        """Return timestamp of latest climater request."""
        timestamp = self._requests.get('climatisation', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def pheater_action_status(self):
        """Return latest status of parking heater request."""
        return self._requests.get('preheater', {}).get('status', 'None')

    @property
    def pheater_action_timestamp(self):
        """Return timestamp of latest parking heater request."""
        timestamp = self._requests.get('preheater', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def honkandflash_action_status(self):
        """Return latest status of honk and flash action request."""
        return self._requests.get('honkandflash', {}).get('status', 'None')

    @property
    def honkandflash_action_timestamp(self):
        """Return timestamp of latest honk and flash request."""
        timestamp = self._requests.get('honkandflash', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def lock_action_status(self):
        """Return latest status of lock action request."""
        return self._requests.get('lock', {}).get('status', 'None')

    @property
    def lock_action_timestamp(self):
        """Return timestamp of latest lock action request."""
        timestamp = self._requests.get('lock', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def timer_action_status(self):
        """Return latest status of departure timer request."""
        return self._requests.get('departuretimer', {}).get('status', 'None')

    @property
    def timer_action_timestamp(self):
        """Return timestamp of latest departure timer request."""
        timestamp = self._requests.get('departuretimer', {}).get('timestamp', DATEZERO)
        return timestamp.isoformat()

    @property
    def refresh_data(self):
        """Get state of data refresh"""
        if self._requests.get('refresh', {}).get('id', False):
            return True
        return False

    @property
    def is_refresh_data_supported(self):
        """Data refresh is supported."""
        if 'ONLINE' in self._connectivities:
            return True

   # Honk and flash
    @property
    def request_honkandflash(self):
        """State is always False"""
        return False

    @property
    def is_request_honkandflash_supported(self):
        """Honk and flash is supported if service is enabled."""
        if self._services.get('rhonk_v1', False):
            return True

    @property
    def request_flash(self):
        """State is always False"""
        return False

    @property
    def is_request_flash_supported(self):
        """Honk and flash is supported if service is enabled."""
        if self._services.get('rhonk_v1', False):
            return True

  # Requests data
    @property
    def request_in_progress(self):
        """Returns the current, or latest, request in progress."""
        try:
            for section in self._requests:
                if self._requests[section].get('id', False):
                    return True
        except:
            pass
        return False

    @property
    def is_request_in_progress_supported(self):
        """Request in progress is supported for Skoda Connect."""
        if 'ONLINE' in self._connectivities:
            return True

    @property
    def request_results(self):
        """Get last request result."""
        data = {
            'latest': self._requests.get('latest', 'N/A'),
            'state': self._requests.get('state', 'N/A'),
        }
        for section in self._requests:
            if section in ['departuretimer', 'batterycharge', 'air-conditioning', 'climatisation', 'refresh', 'lock', 'preheater']:
                if self._requests.get(section, {}).get('timestamp', None) is None:
                    _LOGGER.debug(f'Failed to get latest timestamp for {section} request.')
                timestamp = self._requests.get(section, {}).get('timestamp', DATEZERO)
                data[section] = self._requests[section].get('status', 'N/A')
                data[section+'_timestamp'] = timestamp.isoformat()
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
        if self.is_request_in_progress_supported:
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
