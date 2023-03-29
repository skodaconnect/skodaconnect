"""TESTING"""
import asyncio
import aiohttp
from vwgconnect.platform.mbb.client import MBBClient
from vwgconnect.platform.skoda.client import TechnicalClient


async def main():
    """Async main"""
    vin = ""
    email = ""
    password = ""
    mysess = aiohttp.ClientSession()
    conn_client = MBBClient(mysess)
    result1 = await conn_client.auth(email, password)
    if result1:
        print("CONNECT LOGIN SUCCESS!")
    else:
        exit()
    print(await conn_client.personal_data())
    print()
    print(await conn_client.mbb_status())
    print()
    print(await conn_client.car_data())
    print()
    print(await conn_client.garage())
    print()
    print(await conn_client.home_region(vin))
    print()
    print(await conn_client.status(vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await conn_client.timers(vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(await conn_client.aircon_status(vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(
        await conn_client.charging_status(vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com")
    )
    print()
    print(await conn_client.aux_heater(vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    print(
        await conn_client.trip_stats(
            vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com", period="cyclic"
        )
    )
    print()
    print(await conn_client.position(vin=vin, base="https://fal-3a.prd.eu.dp.vwg-connect.com"))
    print()
    tech = TechnicalClient(mysess)
    await tech.auth(email, password)
    print(await tech.model_image(vin=vin, size="large"))
    print()

    if mysess is not None:
        await mysess.close()


asyncio.run(main())
exit()
