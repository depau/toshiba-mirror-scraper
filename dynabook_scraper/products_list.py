import asyncio

import aiofiles
import aiohttp

from dynabook_scraper.utils.uvloop import async_run
from dynabook_scraper.utils.common import extract_json_var, http_retry, remove_null_fields
from dynabook_scraper.utils.paths import data_dir
from .utils import json


@http_retry
async def scrape_products_list():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://support.dynabook.com/drivers") as response:
            response.raise_for_status()
            page = await response.text()

        all_products = extract_json_var(page, "allProducts")

        # Some URLs have leading/trailing whitespace
        for _, product_type in all_products.items():
            if "pimg" in product_type:
                product_type["pimg"] = product_type["pimg"].strip()
            for family in product_type["family"]:
                if "fimg" in family:
                    family["fimg"] = family["fimg"].strip()

        async with aiofiles.open(data_dir / "all_products.json", "wb") as f:
            # noinspection PyTypeChecker
            await json.adump(remove_null_fields(all_products), f)

        # Generate flat product list
        flat_products = {}
        for pid, product_type in all_products.items():
            for family in product_type["family"]:
                for model in family["models"]:
                    model["pid"] = pid
                    model["fid"] = family["fid"]
                    flat_products[model["mid"]] = model

        async with aiofiles.open(data_dir / "all_products_flat.json", "wb") as f:
            # noinspection PyTypeChecker
            await json.adump(flat_products, f)


def cli_scrape_products_list():
    async_run(scrape_products_list())


if __name__ == "__main__":
    cli_scrape_products_list()
