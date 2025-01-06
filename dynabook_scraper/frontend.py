import shutil
import sys
from pathlib import Path

import jinja2
from jinja2 import select_autoescape

from dynabook_scraper.utils.paths import data_dir

env = jinja2.Environment(
    loader=jinja2.PackageLoader("dynabook_scraper"),
    autoescape=select_autoescape(),
)


def render(name: str, **kwargs) -> str:
    template = env.get_template(name)
    return template.render(**kwargs)


def cli_build_frontend():
    base_url = "/"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]

    env.globals["base_url"] = base_url.rstrip("/")

    with open(data_dir / "index.html", "w") as f:
        f.write(render("home.html"))

    (data_dir / "product").mkdir(exist_ok=True)
    with open(data_dir / "product" / "index.html", "w") as f:
        f.write(render("product.html"))

    (data_dir / "content").mkdir(exist_ok=True)
    with open(data_dir / "content" / "index.html", "w") as f:
        f.write(render("content.html"))

    (data_dir / "eula").mkdir(exist_ok=True)
    with open(data_dir / "eula" / "index.html", "w") as f:
        f.write(render("eula.html"))

    shutil.copy2(Path(__file__).parent / "templates/dlServiceWorker.js", data_dir / "product/dlServiceWorker.js")


if __name__ == "__main__":
    cli_build_frontend()
