"""Constants for Skoda Connect library."""

BASE_SESSION = 'https://msg.volkswagen.de'
BASE_AUTH = 'https://identity.vwgroup.io'
CLIENT_ID = '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com'
XCLIENT_ID = '28cd30c6-dee7-4529-a0e6-b1e07ff90b79'
XAPPVERSION = '3.2.6'
XAPPNAME = 'cz.skodaauto.connect'
USER_AGENT = 'okhttp/3.14.7'
APP_URI = 'skodaconnect://oidc.login/'

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

HEADERS_AUTH = {
    'Connection': 'keep-alive',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
#    'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,\
#        image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
    'Content-Type': 'application/x-www-form-urlencoded',
    'User-Agent': USER_AGENT,
    'X-App-Name': XAPPNAME
}
