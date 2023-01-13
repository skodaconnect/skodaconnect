"""Constants used for all API Clients."""

# Request/response related
TIMEOUT = 20
STATUS = "status"
DATA = "data"
ERROR = "error"
ERROR_DESC = "error_description"
LOCATION = "location"
URL = "url"
SSO = "sso"
REQ_PARAMS = "params"
SIGNIN_SERVICE = "signin-service"
TERMS = "terms-and-conditions"
V1 = "v1"
V2 = "v2"
V3 = "v3"
HTML = "html"
JS = "js"
TYPE = "type"

# HTML form strings
ACTION = "action"
POST_ACTION = "postAction"
EMAIL = "email"
PASSWORD = "password"
HMAC = "hmac"
CRED_PATH = "registerCredentialsPath"
REGISTER = "register"

# Used for tokens
SYSID = "systemId"

# Error strings
ERRORS = {
    "login.error.throttled": "Account is locked",
    "login.errors.password_invalid": "Invalid password",
}
ERROR_DEFAULT = ""
