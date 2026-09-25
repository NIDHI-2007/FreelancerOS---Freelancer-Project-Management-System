"""Application factory for the Freelancer Project Management System API."""

from pathlib import Path

from flask import Flask, send_from_directory

from app.config import Config
from app.db import close_db, get_db
from app.errors import register_error_handlers
from app.extensions import jwt
from app.routes import register_routes


def create_app(test_config=None):
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    # Serve the static web client at the Flask origin so browser requests to
    # /api do not need a separate CORS configuration during the local demo.
    app = Flask(__name__, static_folder=str(frontend_dir), static_url_path="")
    app.config.from_object(Config)
    app.config.setdefault("MAX_CONTENT_LENGTH", 2 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY") or not app.config.get("JWT_SECRET_KEY"):
        raise RuntimeError(
            "Set FLASK_SECRET_KEY and JWT_SECRET_KEY in the environment before starting the API."
        )

    jwt.init_app(app)

    @jwt.token_in_blocklist_loader
    def token_is_revoked(_header, payload):
        cursor = get_db().cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM Revoked_Token WHERE token_jti = %s AND expires_at > UTC_TIMESTAMP()",
                (payload["jti"],),
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    jwt.unauthorized_loader(lambda _reason: _jwt_error("authentication_required", "A valid access token is required."))
    jwt.invalid_token_loader(lambda _reason: _jwt_error("invalid_token", "The access token is invalid."))
    jwt.expired_token_loader(lambda _header, _payload: _jwt_error("expired_token", "The access token has expired."))
    jwt.revoked_token_loader(lambda _header, _payload: _jwt_error("revoked_token", "The access token has been revoked."))

    app.teardown_appcontext(close_db)
    register_error_handlers(app)
    register_routes(app)

    @app.get("/")
    def frontend_index():
        return send_from_directory(app.static_folder, "index.html")

    return app


def _jwt_error(code, message):
    return {"error": {"code": code, "message": message}}, 401
