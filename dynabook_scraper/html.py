import asyncio
import json
from pathlib import Path

import aiohttp
from tqdm import tqdm

from dynabook_scraper.common import data_dir, products_dir, extract_json_var, DebugContext, run_concurrently, html_dir

CONCURRENCY = 20


async def scrape_product_html(ctx: DebugContext, session: aiohttp.ClientSession, mid: str):
    product_dir = products_dir / mid
    product_dir.mkdir(exist_ok=True)

    ctx = ctx.with_values(mid=mid)

    with ctx:
        base_url = f"https://support.dynabook.com/support/modelHome?freeText={mid}"
        async with session.get(base_url) as response:
            response.raise_for_status()
            page = await response.text()

        product_html_dir = html_dir / str(mid)
        product_html_dir.mkdir(exist_ok=True)

        with open(product_html_dir / "base.html", "w") as f:
            f.write(page)

        os_list = [i for i in extract_json_var(page, "partNumOSJSONArr") if i["osId"] != "-1"]
        with open(product_dir / "operating_systems.json", "w") as f:
            json.dump(os_list, f, indent=2)

    for os_obj in os_list:
        with ctx.with_values(os_id=os_obj["osId"]):
            os_id = os_obj["osId"]

            async with session.get(
                f"https://support.dynabook.com/support/modelHome?freeText={mid}&osId={os_id}"
            ) as response:
                response.raise_for_status()
                os_page = await response.text()

            with open(product_html_dir / f"os_{os_id}.html", "w") as f:
                f.write(os_page)


async def scrape_products_html(products_list: Path = data_dir / "all_products_flat.json"):
    with open(products_list) as f:
        all_products = json.load(f)

    ctx = DebugContext()

    filtered_products = {}
    for mid in all_products.keys():
        drivers = products_dir / mid / "html/base.html"
        if drivers.is_file() and drivers.stat().st_size > 0:
            continue

        filtered_products[mid] = all_products[mid]

    progress = tqdm(total=len(filtered_products), desc="Scraping product HTMLs")

    # noinspection PyShadowingNames
    async def coro(mid):
        async with aiohttp.ClientSession() as session:
            name = all_products[mid]["mname"]
            progress.write(f"-> Model: {name} ({mid})")
            await scrape_product_html(ctx.with_values(mname=name), session, mid)
            progress.update()

    await run_concurrently(CONCURRENCY, coro, filtered_products.keys())


def cli_scrape_products_html():
    asyncio.run(scrape_products_html())
