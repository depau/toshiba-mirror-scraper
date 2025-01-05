import abc
import os
import re
import warnings
from pathlib import Path
from typing import Any, Type
from urllib.parse import urlparse

import aiofiles
import aiohttp
import internetarchive
from asgiref.sync import sync_to_async
from duckduckgo_search import DDGS
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
    async def download(self, url: str, out_dir: Path, details: dict[str, Any]) -> dict[str, Any]: ...


class NotFoundError(Exception):
    def __init__(self, url: str, mirror_url: str):
        self.url = url
        self.mirror_url = mirror_url


@register_scavenger
class MementoRescuer(FileRescuerStrategy):
    @http_retry
    async def download(self, url: str, out_dir: Path, details: dict[str, Any]) -> dict[str, Any]:
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


@register_scavenger
class DuckSearchInternetArchiveRescuer(FileRescuerStrategy):
    _ia_url_re = re.compile(r"^https://archive.org/details/([^/]+)$")

    @http_retry
    async def download(self, url: str, out_dir: Path, details: dict[str, Any]) -> dict[str, Any]:
        # Use DuckDuckGo to search for content since file names are not indexed by IA
        ddgs = DDGS()
        filename = Path(url).name

        # noinspection PyArgumentList
        results = await sync_to_async(ddgs.text, thread_sensitive=False)(f"{filename} site:archive.org")

        for result in results:
            # When there's a match, the filename tends to appear in the body
            if not filename in result["body"]:
                continue

            # We only handle Internet Archive direct uploads for now
            match = self._ia_url_re.match(result["href"])
            if not match:
                continue

            ia_id = match.group(1)

            # noinspection PyTypeChecker, PyArgumentList
            files = await sync_to_async(internetarchive.get_files, thread_sensitive=False)(
                ia_id, glob_pattern=[f"*/{filename}", filename]
            )

            if not files:
                continue

            found_file = files[0]
            if "fileSize" in details:
                file_size = details["fileSize"]
                for file in files:
                    if file.size == file_size:
                        found_file = file
                        break
                else:
                    warnings.warn(f"File size mismatch for {filename} in {ia_id}")
                    continue
            elif len(files) > 1:
                warnings.warn(f"Multiple files found for {filename} in {ia_id}: {files}")

            tqdm.write(f"Downloading from Internet Archive: {url}")
            await download_file(found_file.url, out_dir)

            return {
                "mirror_url": found_file.url,
                "rescue_strategy": "internet_archive",
            }

        raise NotFoundError(url, "https://duckduckgo.com")


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
    filename = Path(url).name
    out_dir = downloads_dir / str(cid)
    last_exc: aiohttp.ClientResponseError | NotFoundError | None = None
    for rescuer in rescuers:
        try:
            result = await rescuer.download(url, out_dir, details)
            await write_result_file(cid, url, 200, url, **result)
            break
        except (aiohttp.ClientResponseError, NotFoundError) as e:
            last_exc = e
    else:
        tqdm.write(f"Failed to rescue {url} [{cid}]: {last_exc}")
        if isinstance(last_exc, NotFoundError):
            await write_result_file(cid, url, 404, filename, last_exc.mirror_url)
        else:
            await write_result_file(cid, url, last_exc.status, filename, last_exc.request_info.url.host)


async def scrape_broken_links():
    broken_links = []
    async for details in find_broken_links_content():
        broken_links.append(details)

    progress = tqdm(total=len(broken_links), desc="Scraping broken links")

    async def coro(details):
        await scrape_broken_link(details)
        progress.update()

    await run_concurrently(5, coro, broken_links)


def cli_scrape_broken_links():
    async_run(scrape_broken_links())
