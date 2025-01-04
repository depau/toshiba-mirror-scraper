import os
from pathlib import Path

data_dir = Path(os.environ.get("DATA_DIR", "data"))
data_dir.mkdir(exist_ok=True)

assets_dir = data_dir / "assets"
assets_dir.mkdir(exist_ok=True)

product_assets_dir = assets_dir / "products"
product_assets_dir.mkdir(exist_ok=True)

html_dir = data_dir / "html"
html_dir.mkdir(exist_ok=True)

products_dir = data_dir / "products"
products_dir.mkdir(exist_ok=True)

content_dir = data_dir / "content"
content_dir.mkdir(exist_ok=True)

downloads_dir = assets_dir / "content"
downloads_dir.mkdir(exist_ok=True)
