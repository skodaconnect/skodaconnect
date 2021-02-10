"""Constants for Skoda Connect library."""

BASE_SESSION = 'https://msg.volkswagen.de'
BASE_AUTH = 'https://identity.vwgroup.io'
BRAND = 'skoda'
COUNTRY = 'CZ'

# Headers used in communication
CLIENT_ID = '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com'
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
    'User-Agent': USER_AGENT
}

# Used for authentication
HEADERS_AUTH = {
    'Connection': 'keep-alive',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Content-Type': 'application/x-www-form-urlencoded',
    'x-requested-with': XAPPNAME,
    'User-Agent': USER_AGENT,
    'X-App-Name': XAPPNAME
}

# Different parameters used in authentication
SCOPE = 'openid mbb profile address cars email birthdate badge phone driversLicense dealers'
TOKEN_TYPES = 'code id_token token'
