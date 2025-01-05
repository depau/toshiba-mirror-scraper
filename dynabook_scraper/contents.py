import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiofiles
import aiohttp
import bs4
from tqdm import tqdm

from dynabook_scraper.utils.common import run_concurrently, download_file
from .utils import json
from .utils.paths import content_dir, downloads_dir
from .utils.uvloop import async_run

CONCURRENCY = 10


def handle_error(cid: str, details: dict[str, Any], out_dir: Path):
    shutil.rmtree(out_dir)
    traceback.print_exc()
    with open("errors.txt", "a") as f:
        print(f"Error downloading content [{cid}] {details.get('contentFile')}", file=f)
        traceback.print_exc(file=f)


async def write_result_file(cid: str, url: str, status_code: int, filename: str, source: str):
    result = {
        "contentID": cid,
        "url": url,
        "status_code": status_code,
    }
    if 200 <= status_code < 300:
        result["url"] = f"content/{cid}/{filename}"

    async with aiofiles.open(content_dir / f"{cid}_crawl_result.json", "w") as f:
        await json.adump(result, f)


async def download_from_memento(url: str, out_dir: Path) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://timetravel.mementoweb.org/timegate/{url}", allow_redirects=False) as response:
            if response.status != 302:
                tqdm.write(f"Content not available on timetravel.mementoweb.org: {url}")
                raise aiohttp.ClientResponseError(response.request_info, response.history, status=404)
            response.raise_for_status()

        archive_url = response.headers["Location"]
        hostname = urlparse(archive_url).hostname

        tqdm.write(f"Downloading from Memento {hostname}: {url}")
        await download_file(archive_url, out_dir)


async def download_content(details: dict[str, Any]):
    cid = details["contentID"]
    content_type = details["contentType"]
    out_dir = downloads_dir / str(cid)
    url = None
    filename = None

    try:
        if content_type in ("DL", "UG", "scraper-static-content"):
            url = details.get("contentFile")
            if not url:
                tqdm.write(f"Content file not found: [{cid}] {details.get('contentFile')}")
                return

            filename = Path(url).name
            if (out_dir / filename).is_file() and (
                "fileSize" not in details or details["fileSize"] == (out_dir / filename).stat().st_size
            ):
                return

            try:
                await download_file(url, out_dir)
                await write_result_file(cid, url, 200, filename, "dynabook.com")
            except aiohttp.ClientResponseError as e:
                if e.status == 404:
                    breakpoint()
                    await download_from_memento(url, out_dir)
                    await write_result_file(cid, url, 200, filename, "archive.org")
                else:
                    raise

        elif content_type == "scraper-swf":
            filename = "index.html"
            url = details.get("contentFile")
            assert url, f"Content file not found: [{cid}] {details.get('contentFile')}"
            url_base = url.rsplit("/", 1)[0]
            await download_file(url, out_dir, out_filename="index.html")

            # Read as bytes since it looks like some files are not UTF-8 encoded
            async with aiofiles.open(out_dir / "index.html", "rb") as f:
                html = await f.read()

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

            # Find any scripts or stylesheets
            for tag in soup.find_all(["script", "link"], src=True):
                src = tag["src"]
                if src.startswith("http") or src.startswith("/"):
                    continue
                path = Path(src)
                await download_file(
                    url_base + "/" + src,
                    out_dir / path.parent,
                    out_filename=path.name,
                )

            # Find embedded SWF file
            embed = soup.find("embed")
            if embed:
                await download_file(url_base + "/" + embed["src"], out_dir)

            await write_result_file(cid, url, 200, filename, "dynabook.com")
    except aiohttp.ClientResponseError as e:
        await write_result_file(cid, url, e.status, filename, e.request_info.url.host)
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
        async with aiofiles.open(content_dir / file) as f:
            j = await json.aload(f)
            if "contentID" not in j:
                continue
            details.append(j)

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
    async_run(download_contents())


def cli_download_content():
    content_id = sys.argv[1]

    with open(content_dir / f"{content_id}.json") as f:
        details = json.load(f)

    async_run(download_content(details))
