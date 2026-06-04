import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
os.environ.setdefault("BOWLYZER_ROOT", project_root)
# Dev default: avoid loading full Parquet + warming cache while the UI fires many API calls.
os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
