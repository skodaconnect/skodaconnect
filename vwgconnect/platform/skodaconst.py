"""Constants specific to the Technical client (Skoda Native)."""

# Used in Android app 5.2.7
XCLIENT_ID = "fef89b3d-a6e0-4525-91eb-a9436e6e469a"
XAPPVERSION = "5.2.7"
XAPPNAME = "cz.skodaauto.connect"
USER_AGENT = "okhttp/4.9.3"
APP_URI = "skodaconnect://oidc.login/"

CLIENT = "f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com"
SCOPES = "openid mbb profile"
GRANTS = "code id_token"
SYSTEM_ID = "TECHNICAL"

IDTOKEN = "idToken"
ACCESSTOKEN = "accessToken"
REFRESHTOKEN = "refreshToken"
OPREQS = "operation-requests"

# URLs for API endpoints
BASE_URL = "https://api.connect.skoda-auto.cz/api"
VEHICLE_URL = "https://api.connect.skoda-auto.cz/api/v2/vehicles"  # /{VIN}

CHARGING = "charging"
CHARGECONFIG = "chargingSettings"
CHARGEAMPERE = "maxChargeCurrentAc"
CHARGEUNLOCK = "autoUnlockPlugWhenCharged"
CHARGETARGET = "targetStateOfChargeInPercent"
AIRCON = "air-conditioning"
POSITION = "position"
GARAGE = "garage"
USERS = "users"
VEHICLES = "vehicles"

START = "start"
STOP = "stop"
UPDATE = "UpdateSettings"
