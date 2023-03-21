#!/usr/bin/env python3
# Simple script to test login
"""TESTING"""
import asyncio
import aiohttp
from skodaconnect.api.mbb.client import MBBClient
from skodaconnect.api.technical.client import TechnicalClient

async def main():
    """Async main"""
    vin = ""
    email = ""
    password = ""
    # Create aiohttp session
    mysess = aiohttp.ClientSession()

    """
    The API clients should be considered low level code
    A wrapper should use the "Connect" class and implement the different
    API classes depending on the cars bound to the profile.
    With a "legacy" car it's enough with MBB Class since it inherits Connect.
    Some features need the Technical client such as model image.
    For Enyaq both Connect and Technical classes are needed.
    """
    # Create a new API client
    mbb_client = MBBClient(mysess)

    mbb_auth_result = await conn_client.auth(email, password)
    if mbb_auth_result:
        print("CONNECT LOGIN SUCCESS!")
    else:
        exit()

    # Test a few Class methods for the MBB API
    print(await mbb_client.personal_data())
    print()
    print(await mbb_client.mbb_status())
    print()
    print(await mbb_client.car_data())
    print()
    print(await mbb_client.garage())
    print()
    # The home regions is used for deriving API base URL
    # It's different for different functions, fal-... for get, mal-... for set
    print(await mbb_client.home_region(vin))
    print()
    # Used static base URL, the high level code should handle what to send
    print(await mbb_client.status(vin = vin, base = "https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await mbb_client.timers(vin = vin, base = "https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await mbb_client.aircon_status(vin = vin, base = "https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await mbb_client.charging_status(vin = vin, base = "https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await mbb_client.aux_heater(vin = vin, base = "https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await mbb_client.trip_stats(
        vin = vin,
        base = "https://fal-3a.prd.eu.dp.vwg-connect.com",
        period = "cyclic"
    ))
    print()
    print(await mbb_client.position(
        vin = vin,
        base = "https://fal-3a.prd.eu.dp.vwg-connect.com"
    ))
    print()

    # Create a new API client for the "Technical" API
    tech_client = TechnicalClient(mysess)
    tech_auth_result = await tech_client.auth(email, password)
    if tech_auth_result:
        print("CONNECT LOGIN SUCCESS!")
    else:
        exit()

    # Try fetching model image
    print(await tech_client.model_image(vin=vin, size="large"))
    print()

    # No "logout" is done, should either store tokens for reuse or revoke them

    if mysess is not None:
        await mysess.close()

asyncio.run(main())
exit()