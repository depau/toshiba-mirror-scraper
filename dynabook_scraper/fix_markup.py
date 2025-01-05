import os
import re
import sys
import warnings
from pathlib import Path

import aiofiles
import bs4
from tqdm import tqdm

from dynabook_scraper.utils import json
from dynabook_scraper.utils.common import run_concurrently, download_file
from dynabook_scraper.utils.paths import content_dir, downloads_dir
from dynabook_scraper.utils.uvloop import async_run

toshiba_support_re = re.compile(
    r"(?:https?:)?(?://)?www\.support\.toshiba\.com/sscontent\?contentId=(\d+)",
)
dynabook_support_re = re.compile(
    r"(?:https?:)?(?://)?support\.(?:dynabook|toshiba)\.com/support/viewContentDetail\?contentId=(\d+).*?",
)


async def fix_markup(content_id: str, markup: str) -> str:
    soup = bs4.BeautifulSoup(markup, "html.parser")

    # Fix links
    for a in soup.find_all("a", href=True):
        if match := toshiba_support_re.match(a["href"]) or dynabook_support_re.match(a["href"]):
            a["href"] = f"javascript:openSubDoc('{match.group(1)}', 'DL')"
        elif a["href"].startswith("javascript:") and not ("openSubDoc" in a["href"] or "printMe" in a["href"]):
            warnings.warn(f"Unpatched javascript link: {a['href']}")
        elif "support.toshiba.com" in a["href"]:
            a["href"] = a["href"].replace("support.toshiba.com", "support.dynabook.com")

    # Fix images
    for img in soup.find_all("img", src=True):
        src = img["src"]
        # Fix relative paths
        if not src.startswith("http"):
            if "/content/" in src:
                path = src.split("/content/", 1)[1]
                src = f"https://content.us.dynabook.com/content/{path}"
            else:
                warnings.warn(f"Unpatched image link: {src}")
                continue

        # Fix toshiba.com URLs
        src = src.replace("https://support.toshiba.com/content/", "https://content.us.dynabook.com/content/")

        fname = Path(src).name
        dest_dir = downloads_dir / str(content_id)
        dest_dir.mkdir(exist_ok=True, parents=True)

        await download_file(src, dest_dir, out_filename=fname, skip_existing=True)
        img["src"] = f"../assets/content/{content_id}/{fname}"

    return str(soup)


async def fix_content_markup(content_file_path: Path):
    try:
        async with aiofiles.open(content_file_path) as f:
            try:
                content = await json.aload(f)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for {content_file_path}: {e}")
                return

        cid = content.get("contentID")
        if not cid:
            print(f"Content ID not found in {content_file_path}")
            return

        if "markup_fixed" in content:
            return

        if "packageInstruction" in content:
            content["packageInstruction"] = await fix_markup(cid, content["packageInstruction"])
        for section in content.get("contentDetail", []):
            if "content" in section:
                section["content"] = await fix_markup(cid, section["content"])

        content["markup_fixed"] = True

        async with aiofiles.open(content_file_path, "w") as f:
            await json.adump(content, f)
    except Exception as e:
        print(f"Error fixing markup for {content_file_path}: {e}")
        raise


async def fix_contents_markup():
    files = [i for i in os.listdir(content_dir) if i.endswith(".json") and not i.endswith("_crawl_result.json")]
    progress = tqdm(total=len(files), desc="Fixing content markup", unit="file")

    async def coro(content_file):
        content_file_path = content_dir / content_file
        await fix_content_markup(content_file_path)
        progress.update()

    await run_concurrently(20, coro, files)


def cli_fix_contents_markup():
    async_run(fix_contents_markup())


def cli_fix_content_markup():
    content_id = sys.argv[1]
    content_file_path = content_dir / f"{content_id}.json"
    async_run(fix_content_markup(content_file_path))
