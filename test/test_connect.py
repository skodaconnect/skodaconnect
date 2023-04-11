"""Unit Tests for Connect Platform"""
import aiohttp
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
from aioresponses import aioresponses
from jwt import encode
import pytest

from vwgconnect.platform.connect import ConnectClient

URL_IDENTITY_BASE = "https://identity.vwgroup.io"
URL_OPENID = f"{URL_IDENTITY_BASE}/.well-known/openid-configuration"
URL_AUTHORIZE = f"{URL_IDENTITY_BASE}/oidc/v1/authorize"
URL_SIGNIN = (
    f"{URL_IDENTITY_BASE}/signin-service/v1/signin/f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com?"
    "relayState=e6a0d403fdee1b44c13ae8ccd9865b48c5033007"
)
URL_SIGNIN_POST_USERNAME = (
    f"{URL_IDENTITY_BASE}/signin-service/v1/7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com/login/identifier"
)
URL_SIGNIN_POST_PASSWORD = (
    f"{URL_IDENTITY_BASE}/signin-service/v1/7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com/login/authenticate"
)
URL_SIGNIN_REDIRECT_1 = (
    f"{URL_IDENTITY_BASE}/oidc/v1/oauth/sso?"
    "clientId=f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com&relayState=e6a0d403fdee1b44c13ae8ccd9865b48c5033007"
    "&userId=ad0d7945-4814-43d0-801f-b240453d1e43&HMAC=f19defefd1b4aac009efc080c6c7eae3c7df6e117628d2ebc1ba7dca35e0754e"
)
URL_SIGNIN_REDIRECT_2 = (
    f"{URL_IDENTITY_BASE}/signin-service/v1/consent/users/ad0d7945-4814-43d0-801f-b240453d1e43/"
    "f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com?scopes=openid%20mbb%20profile&"
    f"relayState=e6a0d403fdee1b44c13ae8ccd9865b48c5033007&callback={URL_IDENTITY_BASE}/oidc/v1/oauth/client/"
    "callback&hmac=096ce7850bb72ae1d4815e9f4214e0795d2a827d2b3bd871d0ab64f4e415e560"
)
URL_SIGNIN_REDIRECT_3 = (
    f"{URL_IDENTITY_BASE}/oidc/v1/oauth/client/callback/success?"
    "user_id=ad0d7945-4814-43d0-801f-b240453d1e43&client_id=f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com&"
    "scopes=openid%20mbb%20profile&consentedScopes=openid%20mbb%20profile&relayState="
    "e6a0d403fdee1b44c13ae8ccd9865b48c5033007&hmac=d35d992ca2b785d976c0f6dd43000202ee7a6cfac602654e901e7bd1cf14cbe7"
)
URL_SIGNIN_REDIRECT_4 = (
    "skodaconnect://oidc.login/#state=ltch9FeRJHEKN28I17VJhDbbNJqgKTYDONP+pwdtpeA&code="  # + access_token JWT
)
URL_TOKEN_EXCHANGE = "https://api.connect.skoda-auto.cz/api/v1/authentication/token?systemId=CONNECT"


@pytest.fixture
def response_mock() -> aioresponses:
    """Returns a clean aioresponses object to mock responses in tests."""
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def jwt_auth_token() -> str:
    """Returns an authentication token JWT"""
    iat = datetime.now(tz=timezone.utc)
    exp = iat + timedelta(minutes=10)
    payload = {
        "iat": iat,
        "exp": exp,
        "sub": "ad0d7945-4814-43d0-801f-b240453d1e43",
        "aud": "f9a2359a-b776-46d9-bd0c-db1904343117@apps_vw-dilab_com",
        "acr": "https://identity.vwgroup.io/assurance/loa-2",
        "scp": "openid mbb profile",
        "aat": "identitykit",
        "iss": "https://identity.vwgroup.io",
        "jtt": "authorization_code",
        "nonce": "VRwI0brLXuD9jy9eZPw7UzrPBvuozeqB3dwTlB6E5g0",
        "jti": "76fbc381-3018-4973-9b96-d0e1462e81fe",
    }
    return encode(payload, "secret", algorithm="HS256")


@pytest.fixture
def jwt_access_tokens() -> str:
    """Returns access tokens JWTs"""
    iat = datetime.now(tz=timezone.utc)
    exp = iat + timedelta(minutes=10)

    access_token = {
        "iat": iat,
        "exp": exp,
        "sub": "ad0d7945-4814-43d0-801f-b240453d1e43",
        "aud": "7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com",
        "scp": "openid profile address cars email birthdate badge mbb phone driversLicense dealers profession vin mileage",
        "aat": "identitykit",
        "iss": "https://identity.vwgroup.io",
        "jtt": "access_token",
        "lee": ["SKODA"],
        "jti": "19772fa2-1559-4e72-b43a-4b481e517ed2",
    }

    refresh_token = access_token.copy()
    refresh_token.pop("lee")
    refresh_token.update(
        {
            "acr": "https://identity.vwgroup.io/assurance/loa-2",
            "jtt": "refresh_token",
            "jti": "957db844-3801-44a2-8bd4-59439cbf70cf",
        }
    )

    id_token = access_token.copy()
    id_token.update(
        {
            "at_hash": "sbZSbow3ptxYrgtxHcpSWg",
            "email_verified": "true",
            "cor": "BE",
            "iss": "https://identity.vwgroup.io",
            "jtt": "id_token",
            "type": "identity",
            "nonce": "iJPiyKpBK1ifA6mpNG/9jySL/wNLmHY/xVhSBgsnAcM",
            "aud": [
                "7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com",
                "https://api.vas.eu.dp15.vwg-connect.com",
                "https://api.vas.eu.wcardp.io",
                "https://prod.ece.gauth-vwac.com",
                "VWGMBB01CNAPP1",
                "VWGMBB01DELIV1",
            ],
            "acr": "https://identity.vwgroup.io/assurance/loa-2",
            "jti": "1b9d0436-059d-4f5a-937f-70a5ede94b45",
            "email": "good_user@skoda.com",
        }
    )

    payload = {
        "accessToken": encode(access_token, "secret", algorithm="HS256"),
        "refreshToken": encode(refresh_token, "secret", algorithm="HS256"),
        "idToken": encode(id_token, "secret", algorithm="HS256"),
    }
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_auth(response_mock: aioresponses, jwt_auth_token: str, jwt_access_tokens: str):
    """
    Test success case for the auth method

    TODO:
    * Validate request parameters
    * Validate request forms
    * Validate request headers
    """
    fixtures_path = os.path.join(sys.path[0], "fixtures")
    with open(os.path.join(fixtures_path, "openid-configuration.json"), "r") as fd_openid:
        response_body_openid = fd_openid.read()
    with open(os.path.join(fixtures_path, "signin_page.html"), "r") as fd_signin:
        response_body_signin = fd_signin.read()
    with open(os.path.join(fixtures_path, "signin_page_password.html"), "r") as fd_signin_post:
        response_body_signin_password = fd_signin_post.read()
    response_mock.get(
        URL_OPENID,
        headers={"Content-Type": "application/json"},
        body=response_body_openid,
    )
    response_mock.get(
        re.compile(r"^https://identity\.vwgroup\.io/oidc/v1/authorize.*$"), status=302, headers={"Location": URL_SIGNIN}
    )
    response_mock.get(URL_SIGNIN, headers={"Content-Type": "text/html"}, body=response_body_signin)
    response_mock.post(
        URL_SIGNIN_POST_USERNAME, headers={"Content-Type": "text/html"}, body=response_body_signin_password
    )
    response_mock.post(URL_SIGNIN_POST_PASSWORD, status=302, headers={"Location": URL_SIGNIN_REDIRECT_1})
    response_mock.get(URL_SIGNIN_REDIRECT_1, status=302, headers={"Location": URL_SIGNIN_REDIRECT_2})
    response_mock.get(URL_SIGNIN_REDIRECT_2, status=302, headers={"Location": URL_SIGNIN_REDIRECT_3})
    response_mock.get(
        URL_SIGNIN_REDIRECT_3, status=302, headers={"Location": f"{URL_SIGNIN_REDIRECT_4}{jwt_auth_token}"}
    )
    response_mock.post(
        URL_TOKEN_EXCHANGE,
        headers={"Content-Type": "application/json"},
        body=jwt_access_tokens,
    )

    mysess = aiohttp.ClientSession()
    client = ConnectClient(mysess, api_debug=True)
    client_auth_result = await client.auth("good_user@skoda.com", "s3cr3tp4ss")
    assert client_auth_result
