import asyncio
import json
import os
import shutil
import traceback
from pathlib import Path
from typing import Any

import aiohttp
import bs4
from tqdm import tqdm

from dynabook_scraper.common import content_dir, run_concurrently, download_file, downloads_dir

CONCURRENCY = 10


def handle_error(cid: str, details: dict[str, Any], out_dir: Path):
    shutil.rmtree(out_dir)
    traceback.print_exc()
    with open("errors.txt", "a") as f:
        print(f"Error downloading content [{cid}] {details.get('contentFile')}", file=f)
        traceback.print_exc(file=f)


def write_result_file(cid: str, url: str, status_code: int, filename: str):
    result = {
        "contentID": cid,
        "url": url,
        "status_code": status_code,
    }
    if 200 <= status_code < 300:
        result["url"] = f"content/{cid}/{filename}"

    with open(content_dir / f"{cid}_crawl_result.json", "w") as f:
        f.write(json.dumps(result, indent=2))


async def download_content(details: dict[str, Any]):
    cid = details["contentID"]
    content_type = details["contentType"]
    out_dir = downloads_dir / str(cid)
    url = None
    filename = None

    try:
        if content_type in ("DL", "UG", "scraper-static-content"):
            url = details["contentFile"]
            filename = Path(url).name
            if (out_dir / filename).is_file():
                return
            await download_file(url, out_dir)
            write_result_file(cid, url, 200, filename)

        elif content_type == "scraper-swf":
            filename = "index.html"
            url = details["contentFile"]
            url_base = url.rsplit("/", 1)[0]
            await download_file(url, out_dir, out_filename="index.html")

            with open(out_dir / "index.html") as f:
                html = f.read()

            soup = bs4.BeautifulSoup(html, "html.parser")

            # Find executable file
            a = soup.find_all("a", href=True)
            for link in a:
                if link["href"].startswith("http") or link["href"].startswith("/"):
                    continue
                path = Path(link["href"])
                await download_file(
                    url_base + "/" + link["href"],
                    out_dir / path.parent,
                    out_filename=path.name,
                )

            # Find embedded SWF file
            embed = soup.find("embed")
            if embed:
                await download_file(url_base + "/" + embed["src"], out_dir)

            write_result_file(cid, url, 200, filename)
    except aiohttp.ClientResponseError as e:
        write_result_file(cid, url, e.status, filename)
        if e.status == 404:
            tqdm.write(f"Content not found: [{cid}] {details.get('contentFile')}")
        else:
            handle_error(cid, details, out_dir)
    except Exception:
        handle_error(cid, details, out_dir)


async def download_contents():
    details = []
    for file in tqdm(os.listdir(content_dir), desc="Discovering content to download", unit="file"):
        if not file.endswith(".json") or file.endswith("_crawl_result.json"):
            continue
        with open(content_dir / file) as f:
            details.append(json.load(f))

    def sort_key(detail: dict[str, Any]):
        content_id = detail["contentID"]
        has_result = (content_dir / f"{content_id}_crawl_result.json").is_file()
        return has_result, content_id

    details.sort(key=sort_key)

    progress = tqdm(total=len(details), desc="Downloading contents")

    async def coro(detail: dict[str, Any]):
        await download_content(detail)
        progress.update()

    await run_concurrently(CONCURRENCY, coro, details)


def cli_download_contents():
    asyncio.run(download_contents())
