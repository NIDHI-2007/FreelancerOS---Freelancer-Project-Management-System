"""Consistent JSON error responses for API clients."""

from flask import jsonify
from werkzeug.exceptions import HTTPException
import mysql.connector


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify(error={"code": error.name.lower().replace(" ", "_"), "message": error.description}), error.code

    @app.errorhandler(mysql.connector.Error)
    def handle_database_error(error):
        app.logger.error("Database operation failed: %s", error, exc_info=(type(error), error, error.__traceback__))
        return jsonify(error={"code": "database_unavailable", "message": "The database operation could not be completed."}), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.error("Unhandled API error: %s", error, exc_info=(type(error), error, error.__traceback__))
        return jsonify(error={"code": "internal_server_error", "message": "An unexpected error occurred."}), 500
