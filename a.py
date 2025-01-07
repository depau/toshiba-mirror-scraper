from pathlib import Path

import aiofiles
from tqdm import tqdm

from dynabook_scraper.utils import json
from dynabook_scraper.utils.common import download_file, run_concurrently
from dynabook_scraper.utils.paths import content_dir, data_dir, downloads_dir
from dynabook_scraper.utils.uvloop import async_run


async def process(file: Path):
    if not file.is_file() or not file.name.endswith("_crawl_result.json"):
        return

    content_id = file.name.split("_")[0]

    async with aiofiles.open(file) as f:
        j = await json.aload(f)

        if "actual_size" in j:
            return

        tqdm.write(str(j))

    if j["status_code"] != 200:
        return

    if "rescue_strategy" in j:
        filename = Path(j["original_url"]).name
        mirror_filename = Path(j["mirror_url"]).name

        if filename != mirror_filename:
            bad = downloads_dir / content_id / mirror_filename
            good = downloads_dir / content_id / filename

            if bad.is_file():
                bad.rename(good)
    else:
        filename = Path(j["url"]).name

    j["url"] = f"assets/content/{content_id}/{filename}"

    path = Path(data_dir / j["url"])
    if not path.is_file() and path.parent.is_dir():
        for p in path.parent.iterdir():
            if p.name.lower() == path.name.lower():
                p.rename(path)
                break

    if not path.is_file():
        if not "rescue_strategy" in j:
            async with aiofiles.open(content_dir / f"{content_id}.json") as f:
                cj = await json.aload(f)
            await download_file(cj["contentFile"], downloads_dir / content_id)

    try:
        j["actual_size"] = path.stat().st_size
    except FileNotFoundError:
        breakpoint()

    async with aiofiles.open(file, "w") as f:
        await json.adump(j, f)


async def main():
    await run_concurrently(20, process, list(content_dir.iterdir()))


async_run(main())
