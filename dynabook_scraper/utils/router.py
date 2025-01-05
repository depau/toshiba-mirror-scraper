import asyncio
import os
import traceback
from urllib import request
from urllib.error import URLError

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from tqdm import tqdm


def has_internet():
    try:
        request.urlopen("http://1.1.1.1", timeout=1)
        return True
    except URLError:
        return False


async def reboot_router():
    tqdm.write("Rebooting router...")

    client = SagemcomClient(
        host=os.environ["ROUTER_HOST"],
        username=os.environ["ROUTER_USERNAME"],
        password=os.environ["ROUTER_PASSWORD"],
        authentication_method=EncryptionMethod.SHA512,
        ssl=True,
        verify_ssl=False,
        keep_keys=False,
    )

    await client.login()
    try:
        await client.reboot()
    except Exception:
        tqdm.write("Ignoring exception while restarting the router:")
        traceback.print_exc()

    await asyncio.sleep(10)

    for _ in range(30):
        if has_internet():
            tqdm.write("Router rebooted successfully")
            return
        await asyncio.sleep(10)
