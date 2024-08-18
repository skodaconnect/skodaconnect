"""Constants."""

from datetime import timedelta

BASE_SESSION = "https://msg.volkswagen.de"
BRAND = "skoda"
COUNTRY = "CZ"

CLIENT_ID = "7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com"
SCOPE = (
    "address badge birthdate cars driversLicense dealers email mileage mbb nationalIdentifier "
    "openid phone profession profile vin"
)
TOKEN_TYPES = "code id_token"
SYSTEM_ID = "TECHNICAL"

# IOS App UA = 'MySkoda/230629002 CFNetwork/1474 Darwin/23.0.0'
# Android App UA = "OneConnect/000000157 CFNetwork/1485 Darwin/23.1.0"
USER_AGENT = "OneConnect/000000157 CFNetwork/1485 Darwin/23.1.0"
APP_URI = "myskoda://redirect/login/"

# Used when fetching data
HEADERS_SESSION = {
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Accept-charset": "UTF-8",
    "Accept": "application/json",
    "X-Client-Id": "fef89b3d-a6e0-4525-91eb-a9436e6e469a",
    "X-App-Version": "5.2.7",
    "X-App-Name": "cz.skodaauto.connect",
    "User-Agent": USER_AGENT,
    "tokentype": "IDK_TECHNICAL",
}

# Used for authentication
HEADERS_AUTH = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "x-requested-with": "cz.skodaauto.connect",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Headers used for fetching tokens for different clients
TOKEN_HEADERS = {
    "Accept": "application/json",
    "X-Platform": "Android",
    "Accept-Charset": "UTF-8",
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "Accept-Encoding": "gzip",
    "User-Agent": USER_AGENT,
    "tokentype": "IDK_TECHNICAL",
}

# Constants related to model image URL construction
MODELVIEWL = "w1080"  # Related to image size, large
MODELVIEWS = "main"  # Related to image size, small
MODELAPPID = "ModcwpMobile"  # Client ID, other ID might require other key
MODELAPIKEY = b"P{+!!H:+I#6)SJS_?[_wh6puD#UH*%l:"  # Key used to sign message
MODELAPI = "ms/GetMODCWPImage"  # API base path
MODELHOST = "https://iaservices.skoda-auto.com/"  # API host

# API endpoints
API_BASE = "https://mysmob.api.connect.skoda-auto.cz"

TIMEOUT_30S = timedelta(seconds=30)
