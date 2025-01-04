import asyncio
import json

import aiohttp

from dynabook_scraper.common import data_dir, extract_json_var


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

        with open(data_dir / "all_products.json", "w") as f:
            # noinspection PyTypeChecker
            json.dump(all_products, f, indent=2)

        # Generate flat product list
        flat_products = {}
        for pid, product_type in all_products.items():
            for family in product_type["family"]:
                for model in family["models"]:
                    model["pid"] = pid
                    model["fid"] = family["fid"]
                    flat_products[model["mid"]] = model

        with open(data_dir / "all_products_flat.json", "w") as f:
            # noinspection PyTypeChecker
            json.dump(flat_products, f, indent=2)


def cli_scrape_products_list():
    asyncio.run(scrape_products_list())


if __name__ == "__main__":
    cli_scrape_products_list()
