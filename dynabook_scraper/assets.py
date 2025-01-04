import asyncio
import json
from pathlib import Path

import aiohttp
from tqdm import tqdm

from dynabook_scraper.common import assets_dir, run_concurrently, download_file


async def download_asset(path: str):
    path = path.lstrip("/")
    asset_dir = assets_dir / Path(path).parent
    asset_dir.mkdir(exist_ok=True, parents=True)

    try:
        await download_file(f"https://support.dynabook.com/{path}", asset_dir)
    except aiohttp.ClientResponseError as e:
        if e.status == 404:
            tqdm.write(f"Asset not found: {repr(path)}")
        else:
            raise


async def scrape_assets():
    with open("data/all_products.json") as f:
        all_products = json.load(f)

    assets = []
    for pid, product_type in all_products.items():
        if "pimg" in product_type and product_type["pimg"]:
            assets.append(product_type["pimg"])

        for family in product_type["family"]:
            if "fimg" in family and family["fimg"]:
                assets.append(family["fimg"])

    progress = tqdm(assets, desc="Scraping assets")
    await run_concurrently(10, download_asset, progress)


def cli_scrape_assets():
    asyncio.run(scrape_assets())
