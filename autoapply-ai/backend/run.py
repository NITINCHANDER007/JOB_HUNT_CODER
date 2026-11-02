"""
AutoApply AI - Application entry point.
Run with: python run.py  OR  flask run
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables before anything else (look in parent autoapply-ai folder if needed)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

from app import create_app, db

app = create_app()

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") == "development"
    print(f"Starting AutoApply AI on http://localhost:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
