import json
from functools import lru_cache
from typing import Any

from tqdm import tqdm

from dynabook_scraper.common import data_dir, products_dir, content_dir, assets_dir


@lru_cache(maxsize=81920)
def get_content_info(cid: str) -> dict[str, Any]:
    info = {}
    with open(content_dir / f"{cid}.json") as f:
        info.update(json.load(f))
    result = content_dir / f"{cid}_crawl_result.json"
    if result.is_file():
        with open(result) as f:
            info.update(json.load(f))
    return info


def gen_products_index() -> dict[str, Any]:
    with open(data_dir / "all_products.json") as f:
        all_products = json.load(f)

    with open(data_dir / "all_products_flat.json") as f:
        flat_products = json.load(f)

    families = {}
    for pid, product_type in all_products.items():
        for family in product_type["family"]:
            families[family["fid"]] = family

    progress = tqdm(total=len(flat_products), desc="Generating products indices", unit="products")

    for mid, info in flat_products.items():
        progress.update()
        gen_product_index(all_products, families, info, mid)


def gen_product_index(all_products, families, info, mid):
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
    with open(products_dir / str(mid) / "operating_systems.json") as f:
        _oses = json.load(f)
        oses = {os["osId"]: os["osNameAndType"] for os in _oses}
    # Load knowledge base
    with open(products_dir / str(mid) / "knowledge_base.json") as f:
        kb = json.load(f)
    for item in kb:
        item.update(get_content_info(item["contentID"]))
    product["knowledge_base"] = kb
    # Load manuals and specs
    with open(products_dir / str(mid) / "manuals_and_specs.json") as f:
        manuals_and_specs = json.load(f)
    for item in manuals_and_specs:
        item.update(get_content_info(item["contentID"]))
    product["manuals_and_specs"] = manuals_and_specs
    # Load drivers
    with open(products_dir / str(mid) / "drivers.json") as f:
        drivers = json.load(f)
    for os_id, os_drivers in drivers.items():
        os_name = "Any" if os_id == "generic" else oses[os_id]
        product["drivers"][os_name] = []

        if not os_drivers:
            continue

        for driver in os_drivers:
            driver.update(get_content_info(driver["contentID"]))
            product["drivers"][os_name].append(driver)
    with open(assets_dir / "products" / f"{mid}.json", "w") as f:
        json.dump(product, f, indent=2)


def cli_gen_products_index():
    gen_products_index()
