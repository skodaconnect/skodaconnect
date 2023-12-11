"""Constants for Skoda Connect library."""

BASE_SESSION = 'https://msg.volkswagen.de'
BASE_AUTH = 'https://identity.vwgroup.io'
BRAND = 'skoda'
COUNTRY = 'CZ'

# Data used in communication
CLIENT_LIST = {
    'connect': {
        'CLIENT_ID':    '7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com',       # Client ID for 'CONNECT' service
        'SCOPE':        'openid profile address cars email birthdate badge mbb phone driversLicense dealers profession vin mileage',    # Requests to vwg-connect.com/ msg.volkswagen.de etc...
        'TOKEN_TYPES':  'code id_token',                                                # tokentype=IDK_CONNECT / MBB (API token)
        'SYSTEM_ID':    'CONNECT'                                                       # Most things related to profile or domain vwapps
    },
    'technical': {
        'CLIENT_ID':    'f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com',       # Client ID for Skoda native API
        'SCOPE':        'openid mbb profile',                                           # Requests to api.connect.skoda-auto.cz
        'TOKEN_TYPES':  'code id_token',                                                # tokentype=IDK_TECHNICAL
        'SYSTEM_ID':    'TECHNICAL'                                                     # Most things related to api.connect.skoda-auto.cz
    },
    'cabs': {
        'CLIENT_ID':    '0f365c6e-8fff-41e0-8b02-2733ed1fe67f@apps_vw-dilab_com',       # ???
        'SCOPE':        'openid profile phone we_connect_vehicles',                     # No idea what this is used for
        'TOKEN_TYPES':  'code id_token',                                                # Identified from requests in app 5.2.7
        'SYSTEM_ID':    'CABS'                                                          # tokentype=???
    },
    'dcs': {
        'CLIENT_ID':    '72f9d29d-aa2b-40c1-bebe-4c7683681d4c@apps_vw-dilab_com',       # Used by SMARTLINK Tokens, DCS??
        'SCOPE':        'openid dealers profile email cars address',                    # Requests to consent.vwgroup.io
        'TOKEN_TYPES':  'code id_token',                                                # tokentype=IDK_SMARTLINK
        'SYSTEM_ID':    'DCS'
    },
}

#XCLIENT_ID = '28cd30c6-dee7-4529-a0e6-b1e07ff90b79'                                    # Android app 3.x?
#XCLIENT_ID = 'a83d7e44-c8b7-42b7-b8ca-e478270d2091'                                    # Used in Android app 4.x.x
XCLIENT_ID = 'fef89b3d-a6e0-4525-91eb-a9436e6e469a'                                     # Used in Android app 5.2.7
XAPPVERSION = '5.2.7'
XAPPNAME = 'cz.skodaauto.connect'
# IOS App UA
# USER_AGENT = 'MySkoda/230629002 CFNetwork/1474 Darwin/23.0.0'
# Android App UA
USER_AGENT = 'OneConnect/000000157 CFNetwork/1485 Darwin/23.1.0'
APP_URI = 'skodaconnect://oidc.login/'

# Used when fetching data
HEADERS_SESSION = {
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Accept-charset': 'UTF-8',
    'Accept': 'application/json',
    'X-Client-Id': XCLIENT_ID,
    'X-App-Version': XAPPVERSION,
    'X-App-Name': XAPPNAME,
    'User-Agent': USER_AGENT,
    'tokentype': 'IDK_TECHNICAL'
}

# Used for authentication
HEADERS_AUTH = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'x-requested-with': XAPPNAME,
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
#    'X-App-Name': XAPPNAME
}

# Headers used for fetching tokens for different clients
TOKEN_HEADERS = {
    'vwg': {
        'X-Client-Id': XCLIENT_ID,
        'Accept': 'application/json',
        'X-Platform': 'Android',
        'Accept-Charset': 'UTF-8',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': USER_AGENT,
    },
    'connect': {
        'Accept': 'application/json',
        'X-Platform': 'Android',
        'Accept-Charset': 'UTF-8',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': USER_AGENT,
    },
    'technical': {
        'Accept': 'application/json',
        'X-Platform': 'Android',
        'Accept-Charset': 'UTF-8',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': USER_AGENT,
    },
    'dcs': {
        'Accept': 'application/json',
        'X-Platform': 'Android',
        'Accept-Charset': 'UTF-8',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': USER_AGENT,
    },
    'cabs': {
        'Accept': 'application/json',
        'X-Platform': 'Android',
        'Accept-Charset': 'UTF-8',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip',
        'User-Agent': USER_AGENT,
    }
}

# Request error codes, not yet in use
ERROR_CODES = {
    '11': 'Charger not connected'
}

# Constants related to model image URL construction
MODELVIEWL = 'w1080'                                    # Related to image size, large
MODELVIEWS = 'main'                                     # Related to image size, small
MODELAPPID = 'ModcwpMobile'                             # Client ID, other ID might require other key
MODELAPIKEY = b'P{+!!H:+I#6)SJS_?[_wh6puD#UH*%l:'       # Key used to sign message
MODELAPI = 'ms/GetMODCWPImage'                          # API base path
MODELHOST = 'https://iaservices.skoda-auto.com/'        # API host

### API Endpoints below, not yet in use ###
# API AUTH endpoints
AUTH_OIDCONFIG = 'https://identity.vwgroup.io/.well-known/openid-configuration'                     # OpenID configuration
AUTH_TOKEN = 'https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode'                     # Endpoint for exchanging authcode for token
AUTH_REVOKE = 'https://tokenrefreshservice.apps.emea.vwapps.io/revokeToken'                         # Endpoint for revocation of Skoda tokens
AUTH_REFRESH = 'https://tokenrefreshservice.apps.emea.vwapps.io/refreshTokens'                      # Endpoint for Skoda token refresh
AUTH_TOKENKEYS = 'https://identity.vwgroup.io/oidc/v1/keys'                                         # Signing keys for tokens
AUTH_VWGTOKEN = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token'      # Endpoint for get VWG token
AUTH_VWGREVOKE = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/revoke'    # Endpoint for revoking VWG tokens
AUTH_VWGKEYS = 'https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/public/jwk/v1'                # Signing keys for VWG tokens

# API endpoints
API_HOMEREGION = 'https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion'   # API endpoint to get vehicles home region (base URL)
API_BASEHOME = 'https://mal-1a.prd.ece.vwg-connect.com/api'
API_DEFAULTHOME = 'https://msg.volkswagen.de'                                                       # Default home region
API_REALCARDATA = 'https://customer-profile.apps.emea.vwapps.io/v2/customers/{subject}/realCarData' # API endpoint for car information
API_VEHICLES = 'https://api.connect.skoda-auto.cz/api/v2/garage/vehicles'                           # Garage info
API_STATUS = 'https://api.connect.skoda-auto.cz/api/v1/vehicle-status/{vin}'                        # Vehicle status report
API_CHARGING = 'https://api.connect.skoda-auto.cz/api/v1/charging/{vin}/status'                     # Vehicle charging information (newer cars such as Enyaq iV)
API_OPERLIST = '{homeregion}/api/rolesrights/operationlist/v3/vehicles/{vin}'                       # API Endpoint for supported operations
API_CHARGER = 'fs-car/bs/batterycharge/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger'                 # Charger data
API_CLIMATER = 'fs-car/bs/climatisation/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater'               # Climatisation data
API_TIMER = 'fs-car/bs/departuretimer/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer'                    # Departure timers
API_POSITION = 'fs-car/bs/cf/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/position'                          # Position data
API_TRIP = 'fs-car/bs/tripstatistics/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/tripdata/shortTerm?newest' # Trip statistics
API_HEATER = 'fs-car/bs/rs/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/status'                              # Parking heater
API_REFRESH = 'fs-car/bs/vsr/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests'                          # Force data refresh

# API endpoints for status
REQ_STATUS = {
    'climatisation': 'fs-car/bs/climatisation/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/climater/actions/{id}',
    'batterycharge': 'fs-car/bs/batterycharge/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/charger/actions/{id}',
    'departuretimer': 'fs-car/bs/departuretimer/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/timer/actions/{id}',
    'vsr': 'fs-car/bs/vsr/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests/{id}/jobstatus',
    'default': 'fs-car/bs/{section}/v1/{BRAND}/{COUNTRY}/vehicles/{vin}/requests/{id}/status'
}

# API security pin endpoints
PIN_LOCK = '/api/rolesrights/authorization/v2/vehicles/$vin/services/rlu_v1/operations/LOCK/security-pin-auth-requested'
PIN_UNLOCK = '/api/rolesrights/authorization/v2/vehicles/$vin/services/rlu_v1/operations/UNLOCK/security-pin-auth-requested'
PIN_HEATING = '/api/rolesrights/authorization/v2/vehicles/$vin/services/rheating_v1/operations/P_QSACT/security-pin-auth-requested'
PIN_TIMER = '/api/rolesrights/authorization/v2/vehicles/$vin/services/timerprogramming_v1/operations/P_SETTINGS_AU/security-pin-auth-requested'
PIN_RCLIMA = '/api/rolesrights/authorization/v2/vehicles/$vin/services/rclima_v1/operations/P_START_CLIMA_AU/security-pin-auth-requested'
PIN_COMPLETE = '/api/rolesrights/authorization/v2/security-pin-auth-completed'
