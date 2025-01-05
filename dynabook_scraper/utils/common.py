import asyncio
import random
import re
from pathlib import Path
from typing import Callable, Awaitable, Iterable, Any, List
from urllib.parse import urlparse

import aiofiles
import aiohttp
import duckduckgo_search.exceptions
from multidict import MultiMapping
from tqdm import tqdm

from . import json
from .paths import content_dir


def extract_json_var(script: str, var_name: str):
    match = re.search(rf"var\s+{var_name}\s*=\s*eval\((.*?)\);", script, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Could not find JSON variable {var_name}")

    var = match.group(1)
    return json.loads(var)


async def run_concurrently[T](
    parallel: int,
    func: Callable[..., Awaitable[T]],
    args_iter: Iterable[Any],
) -> List[T]:
    semaphore = asyncio.Semaphore(parallel)

    async def worker(arg: Any) -> T:
        async with semaphore:
            return await func(arg)

    tasks = [asyncio.create_task(worker(arg)) for arg in args_iter]
    results = await asyncio.gather(*tasks)
    return results


async def _handle_ratelimit(e: Exception, iteration: int, headers: MultiMapping[str] | None = None):
    tqdm.write(f"Rate limited: {e} - attempt: {iteration + 1}")
    if headers and "Retry-After" in headers:
        await asyncio.sleep(int(headers["Retry-After"]))
    else:
        await asyncio.sleep(2 ** (iteration + 1) + random.randint(0, 10000) / 1000)


def http_retry[T](fn: Callable[..., T]) -> Callable[..., T]:
    async def wrapper(*args, **kwargs):
        exc = None
        for i in range(7):  # 2**8 = 256 seconds ~= 4 minutes
            try:
                return await fn(*args, **kwargs)
            except (
                aiohttp.ClientConnectorError,
                aiohttp.ConnectionTimeoutError,
                aiohttp.ClientPayloadError,
                TimeoutError,
            ) as e:
                exc = e
                tqdm.write(f"Connection error: {e} - attempt: {i + 1}")
                await asyncio.sleep(2**i)
            except aiohttp.ClientResponseError as e:
                exc = e
                if e.status == 429:
                    await _handle_ratelimit(e, i, e.headers)
                else:
                    raise
            except duckduckgo_search.exceptions.RatelimitException as e:
                exc = e
                await _handle_ratelimit(e, i)
        raise exc

    return wrapper


@http_retry
async def download_file(
    url: str, out_dir: Path, out_filename: str | None = None, session: aiohttp.ClientSession = None
):
    out_dir.mkdir(exist_ok=True, parents=True)
    filename = out_filename or Path(url).name

    session = session or aiohttp.ClientSession()
    async with session:
        async with session.get(url) as response:
            response.raise_for_status()
            size = int(response.headers.get("Content-Length", 0))

            with tqdm(
                total=size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"Downloading {filename}",
                leave=False,
            ) as progress_bar:
                async with aiofiles.open(out_dir / filename, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024):
                        await f.write(chunk)
                        progress_bar.update(len(chunk))


def remove_null_fields[T](obj: T) -> T:
    if isinstance(obj, list):
        return [remove_null_fields(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: remove_null_fields(v) for k, v in obj.items() if v is not None}
    return obj


async def write_result_file(cid: str, url: str, status_code: int, filename: str, mirror_url: str, **additional_info):
    result = {
        "contentID": cid,
        "original_url": url,
        "status_code": status_code,
        "mirror_url": mirror_url,
        "mirror_hostname": urlparse(mirror_url).hostname,
        **additional_info,
    }
    if 200 <= status_code < 300:
        result["url"] = f"content/{cid}/{filename}"

    async with aiofiles.open(content_dir / f"{cid}_crawl_result.json", "w") as f:
        await json.adump(result, f)
