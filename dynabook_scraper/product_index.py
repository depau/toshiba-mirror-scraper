from typing import Any

import aiofiles
from cache import AsyncLRU
from tqdm import tqdm

from dynabook_scraper.utils.common import remove_null_fields, run_concurrently
from .utils import json
from .utils.paths import data_dir, product_dir, products_work_dir, content_dir
from .utils.uvloop import async_run


def filter_content(content: dict[str, Any]) -> dict[str, Any]:
    keep_keys = {
        "contentID",
        "contentType",
        "title",
        "heading",
        "fileVersion",
        "fileSize",
        "orgPubDate",
        "startDate",
        "createDate",
        "status_code",
        "contentFile",
        "mirror_hostname",
        "mirror_url",
        "rescue_strategy",
        "url",
    }
    return {k: v for k, v in content.items() if k in keep_keys}


@AsyncLRU(maxsize=8192)
async def get_content_info(cid: str) -> dict[str, Any] | None:
    if not (content_dir / f"{cid}.json").is_file():
        return None
    info = {}
    async with aiofiles.open(content_dir / f"{cid}.json") as f:
        info.update(await json.aload(f))
    result = content_dir / f"{cid}_crawl_result.json"
    if result.is_file():
        async with aiofiles.open(result) as f:
            info.update(await json.aload(f))
    return filter_content(info)


async def gen_products_index():
    async with aiofiles.open(data_dir / "all_products.json") as f:
        all_products = await json.aload(f)

    async with aiofiles.open(data_dir / "all_products_flat.json") as f:
        flat_products = await json.aload(f)

    families = {}
    for pid, product_type in all_products.items():
        for family in product_type["family"]:
            families[family["fid"]] = family

    progress = tqdm(total=len(flat_products), desc="Generating products indices", unit="products")

    async def coro(mid):
        product_info = flat_products[mid]
        await gen_product_index(all_products, families, product_info, mid)
        progress.update()

    await run_concurrently(10, coro, flat_products.keys())


async def gen_product_index(all_products, families, info, mid):
    product_type = all_products[info["pid"]]
    family = families[info["fid"]]
    product = {
        "name": info["mname"],
        "mid": mid,
        "pid": info["pid"],
        "fid": info["fid"],
        "type": product_type["pname"],
        "product_img": f"assets/{product_type['pimg']}",
        "family": family["fname"],
        "family_img": f"assets/{family['fimg']}",
        "knowledge_base": [],
        "manuals_and_specs": [],
        "drivers": {},
    }

    model_img_link = products_work_dir / str(mid) / "model_img.txt"
    if model_img_link.is_file():
        async with aiofiles.open(model_img_link) as f:
            product["model_img"] = f"assets{(await f.read()).strip()}"

    # Load factory config
    factory_config = products_work_dir / str(mid) / "factory_config.json"
    if factory_config.is_file():
        async with aiofiles.open(factory_config) as f:
            product["factory_config"] = await json.aload(f)

    # Load knowledge base
    async with aiofiles.open(products_work_dir / str(mid) / "knowledge_base.json") as f:
        kb = await json.aload(f)
    for item in kb:
        content = await get_content_info(item["contentID"])
        if content:
            item.update(content)
    product["knowledge_base"] = kb

    # Load manuals and specs
    async with aiofiles.open(products_work_dir / str(mid) / "manuals_and_specs.json") as f:
        manuals_and_specs = await json.aload(f)
    for item in manuals_and_specs:
        content = await get_content_info(item["contentID"])
        if content:
            item.update(content)
    product["manuals_and_specs"] = manuals_and_specs

    # Load drivers
    async with aiofiles.open(products_work_dir / str(mid) / "drivers.json") as f:
        drivers: dict[str, Any] = await json.aload(f)
    product["drivers"] = drivers

    for _, driver in product["drivers"]["contents"].items():
        content = await get_content_info(driver["contentID"])
        if content:
            driver.update(content)

    product = remove_null_fields(product)

    async with aiofiles.open(product_dir / f"{mid}.json", "wb") as f:
        await json.adump(product, f)


def cli_gen_products_index():
    async_run(gen_products_index())
