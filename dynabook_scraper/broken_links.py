import abc
import os
from pathlib import Path
from typing import Any, Type
from urllib.parse import urlparse

import aiofiles
import aiohttp
from tqdm import tqdm

from dynabook_scraper.utils import json
from dynabook_scraper.utils.common import download_file, write_result_file, run_concurrently, http_retry
from dynabook_scraper.utils.paths import content_dir, downloads_dir
from dynabook_scraper.utils.uvloop import async_run

rescuers = []


def register_scavenger(rescuer: Type["FileRescuerStrategy"]):
    rescuers.append(rescuer())
    return rescuer


class FileRescuerStrategy(abc.ABC):
    @abc.abstractmethod
    async def download(self, url: str, out_dir: Path) -> dict[str, Any]: ...


@register_scavenger
class MementoRescuer(FileRescuerStrategy):
    @http_retry
    async def download(self, url: str, out_dir: Path) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://timetravel.mementoweb.org/timegate/{url}", allow_redirects=False
            ) as response:
                response.raise_for_status()
                if response.status != 302:
                    tqdm.write(f"Content not available on timetravel.mementoweb.org: {url}")
                    raise aiohttp.ClientResponseError(response.request_info, response.history, status=response.status)

            archive_url = response.headers["Location"]
            hostname = urlparse(archive_url).hostname

            tqdm.write(f"Downloading from Memento {hostname}: {url}")
            await download_file(archive_url, out_dir)

            return {
                "mirror_url": archive_url,
                "rescue_strategy": "memento",
            }


async def find_broken_links_content():
    for file in tqdm(os.listdir(content_dir), desc="Discovering broken links", unit="file"):
        if not file.endswith("_crawl_result.json"):
            continue
        content_id = file.replace("_crawl_result.json", "")

        async with aiofiles.open(content_dir / file) as f:
            result = await json.aload(f)

        if result["status_code"] == 200:
            continue

        async with aiofiles.open(content_dir / f"{content_id}.json") as f:
            details = await json.aload(f)

        # Other content types are not implemented for now
        if details["contentType"] not in ("DL", "UG", "scraper-static-content"):
            continue

        # Ignore contents with missing links
        if not details.get("contentFile"):
            continue

        yield details


async def scrape_broken_link(details):
    cid = details["contentID"]
    url = details["contentFile"]
    out_dir = downloads_dir / str(cid)
    last_exc: aiohttp.ClientResponseError | None = None
    for rescuer in rescuers:
        try:
            result = await rescuer.download(url, out_dir)
            await write_result_file(cid, url, 200, url, **result)
            break
        except aiohttp.ClientResponseError as e:
            last_exc = e
    else:
        tqdm.write(f"Failed to rescue {url} [{cid}]: {last_exc}")
        await write_result_file(cid, url, last_exc.status, url, last_exc.request_info.url.host)


async def scrape_broken_links():
    broken_links = []
    async for details in find_broken_links_content():
        broken_links.append(details)

    progress = tqdm(total=len(broken_links), desc="Scraping broken links")

    async def coro(details):
        await scrape_broken_link(details)
        progress.update()

    await run_concurrently(15, coro, broken_links)


def cli_scrape_broken_links():
    async_run(scrape_broken_links())
