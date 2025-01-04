import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Awaitable, TypeVar, Iterable, Any, List

import aiohttp
from tqdm import tqdm

data_dir = Path(os.environ.get("DATA_DIR", "data"))
data_dir.mkdir(exist_ok=True)

assets_dir = data_dir / "assets"
assets_dir.mkdir(exist_ok=True)

html_dir = data_dir / "html"
html_dir.mkdir(exist_ok=True)

products_dir = data_dir / "products"
products_dir.mkdir(exist_ok=True)

content_dir = data_dir / "content"
content_dir.mkdir(exist_ok=True)

downloads_dir = assets_dir / "content"
downloads_dir.mkdir(exist_ok=True)


def extract_json_var(script: str, var_name: str) -> dict:
    match = re.search(rf"var\s+{var_name}\s*=\s*eval\((.*?)\);", script, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Could not find JSON variable {var_name}")

    var = match.group(1)
    # try:
    return json.loads(var)
    # except json.JSONDecodeError:
    #     print("Could not parse JSON, trying to evaluate JS")
    #     return js2py.eval_js(var)


T = TypeVar("T")


async def run_concurrently(
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


class DebugContext:
    def __init__(self, values: dict[str, any] = None):
        self._values = values or {}

    def __enter__(self):
        return self._values

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Print the debug context if an exception occurred but do not silence it
        if exc_type:
            print(f"Debug context: {self._values}", file=sys.stderr)

    def with_values(self, **values):
        return DebugContext({**self._values, **values})


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
                with open(out_dir / filename, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024):
                        f.write(chunk)
                        progress_bar.update(len(chunk))
