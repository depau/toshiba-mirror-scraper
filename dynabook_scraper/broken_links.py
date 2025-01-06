import abc
import asyncio
import os
import re
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Type
from urllib.parse import urlparse

import aiofiles
import aiohttp
import bs4
import internetarchive
from asgiref.sync import sync_to_async
from duckduckgo_search import DDGS
from tqdm import tqdm

from dynabook_scraper.utils import json
from dynabook_scraper.utils.common import download_file, write_result_file, run_concurrently, http_retry
from dynabook_scraper.utils.paths import content_dir, downloads_dir, data_dir
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


potential_results: dict[str, dict[str, str]] = defaultdict(dict)
search_cache: dict[str, list[dict[str, str]]] = {}
memento_cache: dict[str, str] = {}

ddgs = DDGS()

TIME_BETWEEN_SEARCHES = 10  # seconds
_last_search_time = 0
_search_lock = asyncio.Lock()


@http_retry
async def ddg_search(query):
    search_fn = sync_to_async(ddgs.text, thread_sensitive=False)
    if query in search_cache:
        return search_cache[query]

    async with _search_lock:
        # Perform internal rate-limiting
        global _last_search_time
        if time.time() - _last_search_time < TIME_BETWEEN_SEARCHES:
            await asyncio.sleep(TIME_BETWEEN_SEARCHES - (time.time() - _last_search_time))
        _last_search_time = time.time()

        results = await search_fn(query)
        search_cache[query] = results
        return results


@register_scavenger
class MementoRescuer(FileRescuerStrategy):
    @http_retry
    async def download(self, url: str, out_dir: Path, details: dict[str, Any]) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            if url in memento_cache:
                if not memento_cache[url]:
                    raise NotFoundError(url, "https://timetravel.mementoweb.org")
                archive_url = memento_cache[url]
            else:
                async with session.get(
                    f"https://timetravel.mementoweb.org/timegate/{url}", allow_redirects=False
                ) as response:
                    response.raise_for_status()
                    if response.status != 302:
                        memento_cache[url] = ""
                        tqdm.write(f"Content not available on timetravel.mementoweb.org: {url}")
                        raise aiohttp.ClientResponseError(
                            response.request_info, response.history, status=response.status
                        )
                archive_url = response.headers["Location"]
                memento_cache[url] = archive_url

        hostname = urlparse(archive_url).hostname

        tqdm.write(f"Downloading from Memento {hostname}: {url}")
        await download_file(archive_url, out_dir)

        fname = Path(archive_url).name
        potential_results[fname.lower()][str((out_dir / fname).stat().st_size)] = archive_url

        return {
            "mirror_url": archive_url,
            "rescue_strategy": "memento",
        }


@register_scavenger
class DuckSearchInternetArchiveRescuer(FileRescuerStrategy):
    _ia_item_url_re = re.compile(r"^https?://archive\.org/details/([^/]+)$")
    _ia_archive_url_re = re.compile(r"^https?://[\w.]*archive\.org/view_archive\.php\?archive=.*$")

    @staticmethod
    async def _get_ia_item_file_url(ia_id: str, filename: str, details: dict[str, Any]) -> tuple[str, int] | None:
        # noinspection PyTypeChecker, PyArgumentList
        all_files = await sync_to_async(internetarchive.get_files, thread_sensitive=False)(ia_id)

        # Add the item files to the potential results
        for file in all_files:
            if "_MACOSX" in file.name:
                continue
            fname = Path(file.name).name.lower()
            potential_results[fname][str(file.size)] = file.url

        files = [
            i
            for i in all_files
            if (i.name.lower().endswith(f"/{filename.lower()}") or i.name.lower() == filename.lower())
            and "_MACOSX" not in i.name
        ]

        if not files:
            return

        found_file = files[0]
        if "fileSize" in details:
            file_size = details["fileSize"]
            for file in files:
                if file.size == file_size:
                    found_file = file
                    break
            else:
                warnings.warn(f"File size mismatch for {filename} in {ia_id}")
                return
        elif len(files) > 1:
            warnings.warn(f"Multiple files found for {filename} in {ia_id}: {files}")

        return found_file.url, found_file.size

    @staticmethod
    @http_retry
    async def _get_ia_archive_content_file_url(
        url: str, filename: str, details: dict[str, Any]
    ) -> tuple[str, int] | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                page = await response.text()

        soup = bs4.BeautifulSoup(page, "html.parser")
        table = soup.find("table")
        assert table, f"No table found in {url}"

        files = []

        for row in table.find_all("tr"):
            link = row.find("a", href=True)
            if not link:
                continue
            size_el = row.find_all("td", id="size")
            assert size_el, f"No size found in {url}"

            if "_MACOSX" in url:
                continue

            url = link["href"]
            fname = Path(link.text).name.lower()
            size = int(size_el[0].text)

            files.append((fname, url, size))
            potential_results[fname][str(size)] = url

        file_size = details.get("fileSize")

        for fname, url, size in files:
            if fname == filename.lower():
                if not file_size or size == file_size:
                    return url, size

        return None

    @http_retry
    async def download(self, url: str, out_dir: Path, details: dict[str, Any]) -> dict[str, Any]:
        # Use DuckDuckGo to search for content since file names are not indexed by IA
        filename = Path(url).name

        found_file_url = None
        strategy = None
        size = 0
        if filename.lower() in potential_results:
            if "fileSize" in details:
                file_size = details["fileSize"]
                files = potential_results[filename.lower()]
                if str(file_size) in files:
                    found_file_url = files[str(file_size)]
                    size = file_size
                    strategy = "potential_results"
            else:
                found_file_url = next(iter(potential_results[filename.lower()].values()))
                strategy = "potential_results"

        if not found_file_url:
            # Try online search
            # noinspection PyArgumentList
            results = await ddg_search(f"{filename} site:archive.org")

            for result in results:
                # When there's a match, the filename tends to appear in the body
                if not filename in result["body"]:
                    continue

                # Internet Archive direct uploads for now
                if match := self._ia_item_url_re.match(result["href"]):
                    ia_id = match.group(1)
                    found_file_url, size = await self._get_ia_item_file_url(ia_id, filename, details)
                    strategy = "internet_archive"
                # Archive content listing pages
                elif self._ia_archive_url_re.match(result["href"]):
                    found_file_url, size = await self._get_ia_archive_content_file_url(
                        result["href"], filename, details
                    )
                    strategy = "internet_archive_archive"
                else:
                    continue

                if found_file_url:
                    break

        if not found_file_url:
            raise NotFoundError(url, "https://duckduckgo.com")

        if found_file_url.startswith("//"):
            found_file_url = f"https:{found_file_url}"

        tqdm.write(f"Downloading from Internet Archive: {url}")
        await download_file(found_file_url, out_dir, size=size)

        return {
            "mirror_url": found_file_url,
            "rescue_strategy": strategy,
        }


async def find_broken_links_content():
    for file in tqdm(os.listdir(content_dir), desc="Discovering broken links", unit="file"):
        if not file.endswith("_crawl_result.json"):
            continue
        content_id = file.replace("_crawl_result.json", "")

        try:
            async with aiofiles.open(content_dir / file) as f:
                result = await json.aload(f)
        except Exception as e:
            tqdm.write(f"Error processing {file}: {e}")
            raise

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


async def scrape_broken_link(details) -> bool:
    cid = details["contentID"]
    url = details["contentFile"]
    filename = Path(url).name
    out_dir = downloads_dir / str(cid)
    last_exc: aiohttp.ClientResponseError | NotFoundError | None = None
    for rescuer in rescuers:
        try:
            result = await rescuer.download(url, out_dir, details)
            await write_result_file(cid, url, 200, url, **result)
            tqdm.write(f"Rescued {url} [{cid}]: {result}")
            return True
        except (aiohttp.ClientResponseError, aiohttp.ClientPayloadError, NotFoundError) as e:
            last_exc = e
            tqdm.write(f"Error for {url} [{cid}]: {e}")
    else:
        tqdm.write(f"Failed to rescue {url} [{cid}]: {last_exc}")
        if isinstance(last_exc, NotFoundError):
            await write_result_file(cid, url, 404, filename, last_exc.mirror_url)
        else:
            await write_result_file(cid, url, last_exc.status, filename, last_exc.request_info.url.host)
    return False


async def scrape_broken_links():
    potential_results_path = data_dir / "potential_results.json"
    if potential_results_path.is_file():
        async with aiofiles.open(potential_results_path) as f:
            potential_results.update(await json.aload(f))

    search_cache_path = data_dir / "search_cache.json"
    if search_cache_path.is_file():
        async with aiofiles.open(search_cache_path) as f:
            search_cache.update(await json.aload(f))

    memento_cache_path = data_dir / "memento_cache.json"
    if memento_cache_path.is_file():
        async with aiofiles.open(memento_cache_path) as f:
            memento_cache.update(await json.aload(f))

    try:
        broken_links = []
        async for details in find_broken_links_content():
            broken_links.append(details)

        progress = tqdm(total=len(broken_links), desc="Scraping broken links")

        rescued_count = 0
        failed_count = 0

        async def coro(details):
            rescued = await scrape_broken_link(details)
            if rescued:
                nonlocal rescued_count
                rescued_count += 1
            else:
                nonlocal failed_count
                failed_count += 1
            progress.update()

        try:
            await run_concurrently(5, coro, broken_links)
        finally:
            tqdm.write(f"Rescued {rescued_count} links, failed to rescue {failed_count} links")

    finally:
        with open(potential_results_path, "w") as f:
            json.dump(potential_results, f)

        with open(search_cache_path, "w") as f:
            json.dump(search_cache, f)

        with open(memento_cache_path, "w") as f:
            json.dump(memento_cache, f)


def cli_scrape_broken_links():
    async_run(scrape_broken_links())
