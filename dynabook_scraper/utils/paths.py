import os
from pathlib import Path

data_dir = Path(os.environ.get("DATA_DIR", "data"))
data_dir.mkdir(exist_ok=True)

assets_dir = data_dir / "assets"
assets_dir.mkdir(exist_ok=True)

product_dir = data_dir / "products"
product_dir.mkdir(exist_ok=True)

work_dir = data_dir / "work"
work_dir.mkdir(exist_ok=True)

html_dir = work_dir / "html"
html_dir.mkdir(exist_ok=True)

products_work_dir = work_dir / "products"
products_work_dir.mkdir(exist_ok=True)

content_dir = data_dir / "content"
content_dir.mkdir(exist_ok=True)

downloads_dir = assets_dir / "content"
downloads_dir.mkdir(exist_ok=True)
