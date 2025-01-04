import asyncio
from pathlib import Path

import aiofiles
import aiohttp
from tqdm import tqdm

from dynabook_scraper.utils.common import (
    extract_json_var,
    run_concurrently,
    http_retry,
)
from .utils import json
from .utils.uvloop import async_run
from .utils.paths import data_dir, html_dir, products_work_dir

CONCURRENCY = 20


@http_retry
async def scrape_product_html(session: aiohttp.ClientSession, mid: str):
    product_dir = products_work_dir / mid
    product_dir.mkdir(exist_ok=True)
    base_url = f"https://support.dynabook.com/support/modelHome?freeText={mid}"
    async with session.get(base_url) as response:
        response.raise_for_status()
        page = await response.text()

    product_html_dir = html_dir / str(mid)
    product_html_dir.mkdir(exist_ok=True)

    async with aiofiles.open(product_html_dir / "base.html", "w") as f:
        await f.write(page)

    os_list = [i for i in extract_json_var(page, "partNumOSJSONArr") if i["osId"] != "-1"]
    async with aiofiles.open(product_dir / "operating_systems.json", "wb") as f:
        await json.adump(os_list, f, indent=2)

    for os_obj in os_list:
        os_id = os_obj["osId"]

        async with session.get(
            f"https://support.dynabook.com/support/modelHome?freeText={mid}&osId={os_id}"
        ) as response:
            response.raise_for_status()
            os_page = await response.text()

        async with aiofiles.open(product_html_dir / f"os_{os_id}.html", "w") as f:
            await f.write(os_page)


async def scrape_products_html(products_list: Path = data_dir / "all_products_flat.json"):
    async with aiofiles.open(products_list) as f:
        all_products = await json.aload(f)

    filtered_products = {}
    for mid in all_products.keys():
        drivers = products_work_dir / mid / "html/base.html"
        if drivers.is_file() and drivers.stat().st_size > 0:
            continue

        filtered_products[mid] = all_products[mid]

    progress = tqdm(total=len(filtered_products), desc="Scraping product HTMLs")

    # noinspection PyShadowingNames
    async def coro(mid):
        async with aiohttp.ClientSession() as session:
            name = all_products[mid]["mname"]
            progress.write(f"-> Model: {name} ({mid})")
            await scrape_product_html(session, mid)
            progress.update()

    await run_concurrently(CONCURRENCY, coro, filtered_products.keys())


def cli_scrape_products_html():
    async_run(scrape_products_html())
