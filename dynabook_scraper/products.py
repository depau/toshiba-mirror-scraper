import asyncio
import json
from pathlib import Path

import aiohttp
from tqdm import tqdm

from dynabook_scraper.common import data_dir, products_dir, extract_json_var, DebugContext, run_concurrently, html_dir

CONCURRENCY = 20


# noinspection JSUnresolvedReference
async def parse_product(ctx: DebugContext, session: aiohttp.ClientSession, mid: str):
    product_dir = products_dir / mid
    product_dir.mkdir(exist_ok=True)

    product_html_dir = html_dir / mid

    ctx = ctx.with_values(mid=mid)

    with ctx:
        with open(product_html_dir / "base.html") as f:
            page = f.read()

        with open(product_dir / "operating_systems.json") as f:
            os_list = json.load(f)

        manuals_and_specs = extract_json_var(page, "manualsSpecsJsonArr")
        with open(product_dir / "manuals_and_specs.json", "w") as f:
            json.dump(manuals_and_specs, f, indent=2)

        kb = extract_json_var(page, "knowledgeBaseJsonArr")
        with open(product_dir / "knowledge_base.json", "w") as f:
            json.dump(kb, f, indent=2)

        drivers = {
            "generic": extract_json_var(page, "driversUpdatesJsonArr"),
        }

        for os_obj in os_list:
            with ctx.with_values(os_id=os_obj["osId"]):
                os_id = os_obj["osId"]

                with open(product_html_dir / f"os_{os_id}.html") as f:
                    os_page = f.read()

                drivers[os_id] = extract_json_var(os_page, "driversUpdatesJsonArr")

        with open(product_dir / "drivers.json", "w") as f:
            json.dump(drivers, f, indent=2)


async def parse_products(products_list: Path = data_dir / "all_products_flat.json"):
    with open(products_list) as f:
        all_products = json.load(f)

    ctx = DebugContext()

    filtered_products = {}
    for mid in all_products.keys():
        drivers = products_dir / mid / "drivers.json"
        if drivers.is_file():
            with open(drivers) as f:
                json.load(f)
                continue

        filtered_products[mid] = all_products[mid]

    progress = tqdm(total=len(filtered_products), desc="Scraping products")

    # noinspection PyShadowingNames
    async def coro(mid):
        async with aiohttp.ClientSession() as session:
            name = all_products[mid]["mname"]
            progress.write(f"-> Model: {name} ({mid})")
            await parse_product(ctx.with_values(mname=name), session, mid)
            progress.update()

    await run_concurrently(CONCURRENCY, coro, filtered_products.keys())


def cli_parse_products_html():
    asyncio.run(parse_products())
