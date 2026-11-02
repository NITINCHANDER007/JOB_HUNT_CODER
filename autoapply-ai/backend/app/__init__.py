"""
AutoApply AI - Flask Application Factory
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Initialize extensions (not bound to app yet)
db = SQLAlchemy()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)


def create_app(config_name: str = None) -> Flask:
    """Application factory: creates and configures the Flask app."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    app = Flask(__name__)

    # --- Configuration ---
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///autoapply.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 86400)
    )
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
    app.config["UPLOAD_FOLDER"] = upload_folder if os.path.isabs(upload_folder) else os.path.join(backend_dir, upload_folder)

    resume_folder = os.getenv("RESUME_FOLDER", "uploads/resumes")
    app.config["RESUME_FOLDER"] = resume_folder if os.path.isabs(resume_folder) else os.path.join(backend_dir, resume_folder)

    screenshot_folder = os.getenv("SCREENSHOT_FOLDER", "uploads/screenshots")
    app.config["SCREENSHOT_FOLDER"] = screenshot_folder if os.path.isabs(screenshot_folder) else os.path.join(backend_dir, screenshot_folder)

    app.config["MAX_CONTENT_LENGTH"] = int(
        os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    )
    app.config["MAX_APPLICATIONS_PER_DAY"] = int(
        os.getenv("MAX_APPLICATIONS_PER_DAY", 50)
    )

    # Ensure upload/log directories exist
    for folder in [
        app.config["UPLOAD_FOLDER"],
        app.config["RESUME_FOLDER"],
        app.config["SCREENSHOT_FOLDER"],
        "logs",
    ]:
        os.makedirs(folder, exist_ok=True)

    # --- Initialize extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(
        app,
        origins=["http://localhost:3000", "http://localhost:5000", "http://localhost:5050", "http://127.0.0.1:5000", "http://127.0.0.1:5050"],
        supports_credentials=True,
    )
    limiter.init_app(app)

    # --- Register Blueprints (inside app context to avoid circular imports) ---
    with app.app_context():
        from app.api.auth import auth_bp
        from app.api.profile import profile_bp
        from app.api.resume import resume_bp
        from app.api.applications import applications_bp
        from app.api.dashboard import dashboard_bp
        from app.api.gmail import gmail_bp
        from app.api.chat import chat_bp
        from app.api.linkedin import linkedin_bp

        app.register_blueprint(auth_bp, url_prefix="/api/auth")
        app.register_blueprint(profile_bp, url_prefix="/api/profile")
        app.register_blueprint(resume_bp, url_prefix="/api/resume")
        app.register_blueprint(applications_bp, url_prefix="/api/applications")
        app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
        app.register_blueprint(gmail_bp, url_prefix="/api/gmail")
        app.register_blueprint(chat_bp, url_prefix="/api/chat")
        app.register_blueprint(linkedin_bp, url_prefix="/api/linkedin")

    # --- Static file serving for frontend ---
    from flask import send_from_directory

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        frontend_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "frontend",
        )
        if path and os.path.exists(os.path.join(frontend_dir, path)):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "index.html")

    # --- Health check ---
    @app.route("/health")
    def health():
        return {"status": "ok", "service": "AutoApply AI"}

    return app
