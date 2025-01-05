from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs

import aiofiles
import bs4
from tqdm import tqdm

from dynabook_scraper.utils.common import (
    extract_json_var,
    run_concurrently,
    remove_null_fields,
)
from .utils import json
from .utils.paths import data_dir, html_dir, products_work_dir
from .utils.uvloop import async_run

CONCURRENCY = 30


# noinspection JSUnresolvedReference
async def parse_product(mid: str):
    product_dir = products_work_dir / mid
    product_dir.mkdir(exist_ok=True)

    product_html_dir = html_dir / mid

    async with aiofiles.open(product_html_dir / "base.html") as f:
        page = await f.read()

    async with aiofiles.open(product_dir / "operating_systems.json") as f:
        os_list = await json.aload(f)

    os_map = {os_obj["osId"]: os_obj["osNameAndType"] for os_obj in os_list}

    # Find model image
    soup = bs4.BeautifulSoup(page, "html.parser")
    model_img = soup.select_one(".model_img img")
    if model_img:
        model_img_src = model_img["src"]
        async with aiofiles.open(product_dir / "model_img.txt", "w") as f:
            await f.write(model_img_src)

    # Find factory configuration
    factory_config_line = None
    for line in page.splitlines():
        if "/support/viewFactoryConfig" in line:
            factory_config_line = line
            break
    if factory_config_line:
        url = factory_config_line.split('"')[1]
        query_string = url.split("?", 1)[1]
        query = parse_qs(query_string)

        mpn = query.get("mpn", ["null"])[0]
        config = query.get("config", ["null"])[0]

        if mpn != "null" and config != "null":
            factory_config = {"mpn": mpn, "config": {}}

            for entry in config.split(","):
                kvp = entry.strip().split("=", 1)
                if len(kvp) < 2:
                    kvp.append("")
                factory_config["config"][kvp[0]] = kvp[1]

            async with aiofiles.open(product_dir / "factory_config.json", "wb") as f:
                await json.adump(factory_config, f)

    # Find manuals and specs
    manuals_and_specs = remove_null_fields(extract_json_var(page, "manualsSpecsJsonArr"))
    async with aiofiles.open(product_dir / "manuals_and_specs.json", "wb") as f:
        await json.adump(manuals_and_specs, f)

    # Find knowledge base
    kb = remove_null_fields(extract_json_var(page, "knowledgeBaseJsonArr"))
    async with aiofiles.open(product_dir / "knowledge_base.json", "wb") as f:
        await json.adump(kb, f)

    # Find drivers
    driver_contents = {}
    drivers = defaultdict(list)

    if os_map:
        first_os = os_list[0]["osId"]
        async with aiofiles.open(product_html_dir / f"os_{first_os}.html") as f:
            os_page = await f.read()
            for driver in remove_null_fields(extract_json_var(os_page, "driversUpdatesJsonArr")):
                content_id = str(driver["contentID"])
                driver["tags"] = driver.get("tags", "").split(",")
                driver["tagNames"] = driver.get("tagNames", "").split(",")
                driver["os"] = [tag for tag in driver["tags"] if tag in os_map]
                driver_contents[content_id] = driver

                if not driver["os"]:
                    drivers["Any"].append(content_id)
                else:
                    for os_id in driver["os"]:
                        drivers[os_map[os_id]].append(content_id)

    async with aiofiles.open(product_dir / "drivers.json", "wb") as f:
        await json.adump({"contents": driver_contents, "drivers": drivers}, f)


async def parse_products(products_list: Path = data_dir / "all_products_flat.json"):
    async with aiofiles.open(products_list) as f:
        all_products = await json.aload(f)

    progress = tqdm(total=len(all_products), desc="Scraping products")

    # noinspection PyShadowingNames
    async def coro(mid):
        try:
            await parse_product(mid)
            progress.update()
        except Exception as e:
            print(f"Error parsing product {mid}: {e}")
            raise

    await run_concurrently(CONCURRENCY, coro, all_products.keys())


def cli_parse_products_html():
    async_run(parse_products())
