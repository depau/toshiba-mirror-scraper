from pathlib import Path

import aiofiles
import aiohttp
from tqdm import tqdm

from dynabook_scraper.utils.common import run_concurrently, download_file
from .utils import json
from .utils.paths import assets_dir, products_work_dir, data_dir
from .utils.uvloop import async_run


async def download_asset(path: str):
    path = path.lstrip("/")
    asset_dir = assets_dir / Path(path).parent
    asset_dir.mkdir(exist_ok=True, parents=True)

    try:
        await download_file(f"https://support.dynabook.com/{path}", asset_dir)
    except aiohttp.ClientResponseError as e:
        if e.status == 404:
            tqdm.write(f"Asset not found: {repr(path)}")
        elif e.status == 403:
            tqdm.write(f"Access denied: {repr(path)}")
        else:
            raise


async def scrape_assets():
    async with aiofiles.open(data_dir / "all_products.json") as f:
        all_products = await json.aload(f)

    assets = set()
    for pid, product_type in all_products.items():
        if "pimg" in product_type and product_type["pimg"]:
            assets.add(product_type["pimg"])

        for family in product_type["family"]:
            if "fimg" in family and family["fimg"]:
                assets.add(family["fimg"])

    for file in products_work_dir.glob("*/model_img.txt"):
        async with aiofiles.open(file) as f:
            assets.add((await f.read()).strip())

    progress = tqdm(assets, desc="Scraping assets")

    async def coro(path):
        await download_asset(path)
        progress.update()

    await run_concurrently(30, coro, assets)


def cli_scrape_assets():
    async_run(scrape_assets())
