import asyncio
from pathlib import Path

import aiofiles
import aiohttp
from tqdm import tqdm

from dynabook_scraper.utils.common import (
    extract_json_var,
    run_concurrently,
    remove_null_fields,
)
from .utils import json
from .utils.uvloop import async_run
from .utils.paths import data_dir, html_dir, products_work_dir

CONCURRENCY = 20


# noinspection JSUnresolvedReference
async def parse_product(session: aiohttp.ClientSession, mid: str):
    product_dir = products_work_dir / mid
    product_dir.mkdir(exist_ok=True)

    product_html_dir = html_dir / mid

    async with aiofiles.open(product_html_dir / "base.html") as f:
        page = await f.read()

    async with aiofiles.open(product_dir / "operating_systems.json") as f:
        os_list = await json.load(f)

    manuals_and_specs = remove_null_fields(extract_json_var(page, "manualsSpecsJsonArr"))
    async with aiofiles.open(product_dir / "manuals_and_specs.json", "wb") as f:
        await json.adump(manuals_and_specs, f, indent=2)

    kb = remove_null_fields(extract_json_var(page, "knowledgeBaseJsonArr"))
    async with aiofiles.open(product_dir / "knowledge_base.json", "wb") as f:
        await json.adump(kb, f, indent=2)

    driver_contents = {}

    def ingest_drivers(driver_contents_list):
        if not driver_contents_list:
            return
        for driver in remove_null_fields(driver_contents_list):
            content_id = str(driver["contentID"])
            driver_contents[content_id] = driver
            yield content_id

    drivers = {
        "Any": list(ingest_drivers(extract_json_var(page, "driversUpdatesJsonArr"))),
    }

    for os_obj in os_list:
        os_id = os_obj["osId"]
        os_name = os_obj["osNameAndType"]

        async with aiofiles.open(product_html_dir / f"os_{os_id}.html") as f:
            os_page = await f.read()

        drivers[os_name] = list(ingest_drivers(extract_json_var(os_page, "driversUpdatesJsonArr")))

    async with aiofiles.open(product_dir / "drivers.json", "wb") as f:
        await json.adump(
            {"contents": driver_contents, "drivers": drivers},
            f,
            indent=2,
        )


async def parse_products(products_list: Path = data_dir / "all_products_flat.json"):
    async with aiofiles.open(products_list) as f:
        all_products = await json.aload(f)

    progress = tqdm(total=len(all_products), desc="Scraping products")

    # noinspection PyShadowingNames
    async def coro(mid):
        async with aiohttp.ClientSession() as session:
            await parse_product(session, mid)
            progress.update()

    await run_concurrently(CONCURRENCY, coro, all_products.keys())


def cli_parse_products_html():
    async_run(parse_products())
