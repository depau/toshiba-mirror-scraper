import sys
from datetime import datetime
from typing import Generator

from tqdm import tqdm

from dynabook_scraper.utils.paths import content_dir, product_dir, data_dir


def gen_sitemap_urls(web_prefix: str) -> Generator[str, None, None]:
    web_prefix = web_prefix.rstrip("/")

    yield f"{web_prefix}/"
    yield f"{web_prefix}/eula/"

    for file in tqdm(list(content_dir.iterdir()), desc="Mapping content", unit="files"):
        if not file.is_file() or not file.name.endswith(".json") or file.name.endswith("_crawl_result.json"):
            continue
        cid = file.stem
        yield f"{web_prefix}/content/?contentID={cid}"

    for file in tqdm(list(product_dir.iterdir()), desc="Mapping products", unit="files"):
        if not file.is_file() or not file.name.endswith(".json"):
            continue
        mid = file.stem
        yield f"{web_prefix}/product/?mid={mid}"


def gen_sitemap(web_prefix: str) -> Generator[str, None, None]:
    yield '<?xml version="1.0" encoding="UTF-8"?>'
    yield '<urlset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd" xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'

    now = datetime.now().strftime("%Y-%m-%d")

    for url in gen_sitemap_urls(web_prefix):
        yield f"<url><loc>{url}</loc><lastmod>{now}</lastmod></url>"

    yield "</urlset>"


def cli_gen_sitemap():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <web_prefix>")
        sys.exit(1)

    web_prefix = sys.argv[1]

    with open(data_dir / "sitemap.xml", "w") as f:
        for line in gen_sitemap(web_prefix):
            print(line, file=f)
