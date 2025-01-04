import asyncio
import dataclasses
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, OrderedDict
from urllib.parse import urlencode

import aiofiles
import aiohttp
import bs4
from tqdm import tqdm

from dynabook_scraper.utils.common import run_concurrently, remove_null_fields, http_retry
from .utils.uvloop import async_run
from .utils.paths import products_dir, content_dir
from .utils import json


@dataclass
class Content:
    contentID: str
    contentType: str
    sor: str | None
    freeText: str | None = None


class ContentDownloader:
    def __init__(self):
        self.contents: Dict[str, Content] = {}
        self.downloaded_ids = set()

    def ingest(self, content: dict[str, Any]):
        cid = content["contentID"]
        ctype = content["contentType"]
        sor = content.get("sor") or "undefined"
        c = Content(cid, ctype, sor)

        if cid in self.contents and self.contents[cid] != c:
            print(f"Duplicate content ID with different content: {cid}")
            print(f"Previous content: {self.contents[cid]}")
            print(f"New content: {c}")
            raise ValueError(f"Duplicate content ID with different content: {cid}")
        else:
            self.contents[cid] = c

    def add_version(self, base_content: Content, new_id: str):
        new_content = dataclasses.replace(base_content, contentID=new_id, sor="undefined")
        if new_id not in self.contents:
            self.contents[new_id] = new_content

    @http_retry
    async def _fetch_regular_content(self, content: Content) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            params = OrderedDict[str, str]()
            params["contentType"] = content.contentType
            params["contentId"] = content.contentID
            params["cipherKey"] = ""

            match content.contentType:
                case "DL" | "UG":  # Download (drivers) | User guide
                    params["sor"] = content.sor
                case "IA" | "SB":  # Issue alert | Support bulletin
                    params["freeText"] = content.freeText
                case _:
                    raise ValueError(f"Unsupported content type: {content.contentType}")

            async with session.get(
                f"https://support.dynabook.com/support/contentDetail?{urlencode(params)}",
            ) as response:
                response.raise_for_status()
                resp = await response.json()

                # Ingest previous versions
                if "contentVersion" in resp and resp["contentVersion"]:
                    for version in resp["contentVersion"]:
                        self.add_version(content, version["contentID"])

                return remove_null_fields(resp)

    @staticmethod
    @http_retry
    async def _fetch_static_content(content: Content) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://support.dynabook.com/support/staticContentDetail?contentId={content.contentID}&isFromTOCLink=false",
            ) as response:
                response.raise_for_status()
                page = await response.text()

            soup = bs4.BeautifulSoup(page, "html.parser")
            iframe = soup.find("iframe")

            if not iframe:
                raise ValueError("Could not find iframe in static content")

            if iframe.attrs["type"] == "application/pdf":
                return {
                    "contentID": content.contentID,
                    "contentType": "scraper-static-content",
                    "contentFile": iframe.attrs["src"],
                }
            elif iframe.attrs["type"] == "text/html":
                return {
                    "contentID": content.contentID,
                    "contentType": "scraper-swf",
                    "originalContentType": content.contentType,
                    "contentFile": iframe.attrs["src"],
                }
            else:
                raise ValueError(f"Unsupported iframe type: {iframe.attrs['type']}")

    async def _fetch_content_details(self, content: Content) -> dict[str, Any]:
        if content.contentType in (
            "TP",  # Tech pack
            "PC",  # Parts catalog
        ):
            raise ValueError(f"Unsupported content type: {content.contentType}")

        if content.contentType in (
            "DL",  # Download (drivers)
            "UG",  # User guide
            "IA",  # Issue alert
            "SB",  # Support bulletin
        ):
            return await self._fetch_regular_content(content)

        if content.contentType in (
            "PT",  # Product tour (SWF)
            "DS",  # Detailed specs (PDF)
            "RG",  # Resource guide (PDF)
            "MM",  # Maintenance manual (PDF)
            "QSG",  # Quick start guide (PDF)
        ):
            return await self._fetch_static_content(content)

    async def download_content_details(self, content: Content):
        try:
            details = await self._fetch_content_details(content)
        except aiohttp.client_exceptions.ContentTypeError:
            tqdm.write(f"Warning: Failed to fetch content details for {content} due to invalid content type")
            return

        async with aiofiles.open(content_dir / f"{content.contentID}.json", "wb") as f:
            await json.adump(details, f, indent=2)

    async def download_contents(self):
        progress = tqdm(total=len(self.contents), desc="Downloading contents")

        async def coro(content: Content):
            await self.download_content_details(content)
            progress.update()
            self.downloaded_ids.add(content.contentID)

            # Refresh the progress bar total in case new versions were added
            progress.total = len(self.contents)
            progress.refresh()

        while len(self.contents) > len(self.downloaded_ids):
            opaque_iterator = (i for i in self.contents.values() if i.contentID not in self.downloaded_ids)
            await run_concurrently(20, coro, opaque_iterator)


def gather_drivers(downloader: ContentDownloader):
    driver_jsons = products_dir.glob("*/drivers.json")

    for f in tqdm(list(driver_jsons), desc="Gathering drivers", unit="file"):
        with open(f) as file:
            j = json.load(file)

            for _, driver in j["contents"].items():
                downloader.ingest(driver)


def gather_knowledge_base(downloader: ContentDownloader):
    kb_jsons = products_dir.glob("*/knowledge_base.json")

    for f in tqdm(list(kb_jsons), desc="Gathering knowledge base", unit="file"):
        with open(f) as file:
            j = json.load(file)

            for kb in j:
                downloader.ingest(kb)


def gather_manuals_and_specs(downloader: ContentDownloader):
    manuals_jsons = products_dir.glob("*/manuals_and_specs.json")

    for f in tqdm(list(manuals_jsons), desc="Gathering manuals and specs", unit="file"):
        with open(f) as file:
            j = json.load(file)

            for manual in j:
                downloader.ingest(manual)


def cli_scrape_driver_contents():
    downloader = ContentDownloader()
    gather_drivers(downloader)
    async_run(downloader.download_contents())


def cli_scrape_kb_contents():
    downloader = ContentDownloader()
    gather_knowledge_base(downloader)
    async_run(downloader.download_contents())


def cli_scrape_manuals_contents():
    downloader = ContentDownloader()
    gather_manuals_and_specs(downloader)
    async_run(downloader.download_contents())
