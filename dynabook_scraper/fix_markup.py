import re
import warnings
from pathlib import Path
from typing import Any

import bs4
from tqdm import tqdm

from dynabook_scraper.utils.common import download_file
from dynabook_scraper.utils.paths import downloads_dir

toshiba_support_re = re.compile(
    r"(?:https?:)?(?://)?www\.support\.toshiba\.com/sscontent\?contentId=(\d+)",
)
dynabook_support_re = re.compile(
    r"(?:https?:)?(?://)?support\.(?:dynabook|toshiba)\.com/support/viewContentDetail\?contentId=(\d+).*?",
)
static_content_re = re.compile(
    r"(?:https?:)?(?://)?support\.(?:dynabook|toshiba)\.com/support/staticContentDetail\?contentId=(\d+).*?",
)


async def fix_markup(content_id: str, markup: str) -> str:
    soup = bs4.BeautifulSoup(markup, "html.parser")

    # Fix links
    for a in soup.find_all("a", href=True):
        if (
            match := toshiba_support_re.match(a["href"])
            or dynabook_support_re.match(a["href"])
            or static_content_re.match(a["href"])
        ):
            a["href"] = f"javascript:openSubDoc('{match.group(1)}', 'DL')"
        elif a["href"].startswith("javascript:") and not ("openSubDoc" in a["href"] or "printMe" in a["href"]):
            warnings.warn(f"Unpatched javascript link: {a['href']}")
        elif "support.toshiba.com" in a["href"]:
            a["href"] = a["href"].replace("support.toshiba.com", "support.dynabook.com")

    # Fix images
    for img in soup.find_all("img", src=True):
        src = img["src"]

        if src.startswith("data:image/"):
            continue

        # Fix toshiba.com URLs
        src = src.replace("https://support.toshiba.com/content/", "https://content.us.dynabook.com/content/")

        # Fix known offline hosts
        if "csd.toshiba.com" in src or "forums.toshiba.com" in src:
            src = f"https://timetravel.mementoweb.org/timegate/{src}"

        # Fix relative paths
        if not src.startswith("http"):
            if "/content/" in src:
                path = src.split("/content/", 1)[1]
                src = f"https://content.us.dynabook.com/content/{path}"
            elif "/images/support/" in src:
                path = src.split("/images/support/", 1)[1]
                src = f"https://support.dynabook.com/images/support/{path}"
            elif "/images/ui2/" in src:
                path = src.split("/images/ui2/", 1)[1]
                src = f"https://support.dynabook.com/images/ui2/{path}"
            else:
                warnings.warn(f"Unpatched image link: {src}")
                continue

        fname = Path(src).name
        dest_dir = downloads_dir / str(content_id)
        dest_dir.mkdir(exist_ok=True, parents=True)

        try:
            await download_file(src, dest_dir, out_filename=fname, skip_existing=True)
        except Exception as e:
            warnings.warn(f"Failed to download {src}: {e}")
            continue
        img["src"] = f"../assets/content/{content_id}/{fname}"

    return str(soup)


async def fix_content_markup(content: dict[str, Any]) -> dict[str, Any]:
    cid = content.get("contentID")
    if not cid:
        tqdm.write(f"Content ID not found in content: {content}")
        return content

    if "markup_fixed" in content:
        return content

    if "packageInstruction" in content:
        content["packageInstruction"] = await fix_markup(cid, content["packageInstruction"])
    for section in content.get("contentDetail", []):
        if "content" in section:
            section["content"] = await fix_markup(cid, section["content"])

    content["markup_fixed"] = True
    return content
