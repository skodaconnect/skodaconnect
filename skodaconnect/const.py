"""Constants for Skoda Connect library."""

BASE_SESSION = 'https://msg.volkswagen.de'
BASE_AUTH = 'https://identity.vwgroup.io'
BRAND = 'skoda'
COUNTRY = 'CZ'

# Data used in communication
CLIENT = {
    'connect': {
        'CLIENT_ID':    '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com',     # client id for VWG API, Skoda Connect Services
        'SCOPE':        'openid mbb profile cars address email birthdate badge phone driversLicense dealers profession vin',    # Requests to vwg-connect.com/ msg.volkswagen.de etc...
        'TOKEN_TYPES':  'code id_token'                                                 #tokentype=IDK_CONNECT / MBB (API token)
    },
    'skoda': {
        'CLIENT_ID':    'f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com',       # Provides access to new API? tokentype=IDK_TECHNICAL..
        'SCOPE':        'openid mbb profile',                                           # Requests to api.connect.skoda-auto.cz
        'TOKEN_TYPES':  'code id_token'                                                 # tokentype=IDK_TECHNICAL
    },
    'smartlink': {
        'CLIENT_ID':    '72f9d29d-aa2b-40c1-bebe-4c7683681d4c@apps_vw-dilab_com',       # SMARTLINK Tokens
        'SCOPE':        'openid dealers profile email cars address',                    # Requests to consent.vwgroup.io
        'TOKEN_TYPES':  'code id_token'                                                 # tokentype=IDK_SMARTLINK
    },
}



XCLIENT_ID = '28cd30c6-dee7-4529-a0e6-b1e07ff90b79'
XAPPVERSION = '3.2.6'
XAPPNAME = 'cz.skodaauto.connect'
USER_AGENT = 'okhttp/3.14.7'
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
    'Connection': 'keep-alive',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Content-Type': 'application/x-www-form-urlencoded',
    'x-requested-with': XAPPNAME,
    'User-Agent': USER_AGENT,
    'X-App-Name': XAPPNAME
}
