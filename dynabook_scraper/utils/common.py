import asyncio
import re
from pathlib import Path
from typing import Callable, Awaitable, Iterable, Any, List

import aiofiles
import aiohttp
from tqdm import tqdm

from . import json


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


def http_retry[T](fn: Callable[..., T]) -> Callable[..., T]:
    async def wrapper(*args, **kwargs):
        exc = None
        for i in range(3):
            try:
                return await fn(*args, **kwargs)
            except (aiohttp.ClientConnectorError, aiohttp.ConnectionTimeoutError) as e:
                tqdm.write(f"Connection error: {e} - attempt: {i + 1}")
                exc = e
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
