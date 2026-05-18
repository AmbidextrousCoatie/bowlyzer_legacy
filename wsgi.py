import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
os.environ.setdefault("BOWLYZER_ROOT", project_root)

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
