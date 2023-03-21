"""Constants used for all API Clients."""
# URLs for API endpoints
OPENID_URL = "https://identity.vwgroup.io/.well-known/openid-configuration"

# Request/response related
TIMEOUT = 20
STATUS = "status"
SETTINGS = "settings"
TIMERS = "timers"
IDENTITIES = "identities"
MODE = "mode"
PARK_POS = "parking-position"
DATA = "data"
SSO = "sso"
SIGNIN_SERVICE = "signin-service"
TERMS = "terms-and-conditions"
V1 = "v1"
V2 = "v2"
V3 = "v3"
HTML = "html"
JS = "js"
TYPE = "type"
VIN = "vin"
STOP = "stop"
START = "start"

# HTML form strings
ACTION = "action"
ACTIONS = "actions"
POST_ACTION = "postAction"
EMAIL = "email"
PASSWORD = "password"
HMAC = "hmac"
CRED_PATH = "registerCredentialsPath"
REGISTER = "register"

# Error strings
ERROR = "error"
ERROR_DESC = "error_description"
ERRORS = {
    "login.error.throttled": "Account is locked",
    "login.errors.password_invalid": "Invalid password",
}
ERROR_DEFAULT = "An error occured."

# HTTP Headers
XAPP_NAME = "X-App-Name"
XAPP_VER = "X-App-Version"
XRATE_REMAIN = "X-RateLimit-Remaining"
XREQ_WITH = "X-Requested-With"
XCLIENT_ID = "X-Client-Id"
APP_JSON = "application/json"
APP_FORM = "application/x-www-form-urlencoded"
REFERER = "referer"
LOCATION = "location"
URL = "url"
ORIGIN = "origin"
ACCEPT = "accept"
AUTHZ = "authorization"
BEARER = "Bearer"
CONTENT = "Content-Type"
# HTTP Methods
HTTP_GET = "GET"
HTTP_POST = "POST"
# HTTP Status codes
HTTP_OK = 200
HTTP_EMPTY = 204
HTTP_MOVED = 301
HTTP_REDIR = 302
HTTP_OTHER = 303
HTTP_BADREQ = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_UNALLOWED = 405
HTTP_THROTTLED = 429
HTTP_INTSRVERR = 500
HTTP_BADGW = 502
HTTP_UNAVAILABLE = 503
# HTTP Error messages
HTTP_ERRORS = {
    HTTP_BADREQ: "Invalid request.",
    HTTP_UNAUTHORIZED: "Not authorized.",
    HTTP_FORBIDDEN: "Forbidden request.",
    HTTP_THROTTLED: "Too many requests.",
    HTTP_INTSRVERR: "Service temporarily unavailable.",
    HTTP_BADGW: "Server error. Try again later.",
    HTTP_UNAVAILABLE: "Server error. Try again later."
}
HTTP_ERROR = "Unexpected response."
# HTTP Payload related
PARAMS = "params"
JSON = "json"

# JWT Related
TOKEN = "token"
TOKENTYPE = "tokentype"
TOKENHINT = "token_type_hint"
CODE = "code"
AUTHZ_CODE = "authorizationCode"
AUTHZ_ENDPOINT = "authorization_endpoint"
ISSUER = "issuer"
SYSID = "systemId"
ID_TOKEN = "id_token"
IDTOKEN = "idToken"
ACCESS_TOKEN = "access_token"
ACCESSTOKEN = "accessToken"
REFRESH_TOKEN = "refresh_token"
REFRESHTOKEN = "refreshToken"
SCOPE = "scope"
SCOPE_ID = "scopeId"
REDIR_URI = "redirect_uri"
NONCE = "nonce"
STATE = "state"
RES_TYPE = "response_type"
GRANT_TYPE = "grant_type"
CLIENT_ID = "client_id"
CONSENT = "consent"
CONSENT_SCOPES = "consentedScopes"
MANDATORY_FIELDS = "commonMandatoryFields"
REFRESH = "refresh"
REVOKE = "revoke"
SUBJECT = "sub"
EXPIRY = "exp"
SIG_VERIFY = "verify_signature"

# URLs for API endpoints
SKODA_TOKEN = "https://api.connect.skoda-auto.cz/api/v1/authentication/token"

# Constants related to model image
SMALL = "small"
LARGE = "large"
MODELVIEWL = 'w1080'                               # image size large
MODELVIEWS = 'main'                                # image size small
IMAGESIZE = {
    SMALL: MODELVIEWS,
    LARGE: MODELVIEWL
}
MODELAPPID = 'ModcwpMobile'                        # Client ID
MODELAPIKEY = b'P{+!!H:+I#6)SJS_?[_wh6puD#UH*%l:'  # Key used to sign message
MODELAPI = 'ms/GetMODCWPImage'                     # API base path
MODELURL = 'https://iaservices.skoda-auto.com'     # API host

VIEW = "view"
DATE = "date"
SIGN = "sign"
APPID = "appId"
NEWLINE = "\n"
