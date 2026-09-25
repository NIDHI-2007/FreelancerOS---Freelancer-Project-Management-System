"""Request-scoped MySQL connection management."""

import mysql.connector
from flask import current_app, g


def get_db():
    if "db_connection" not in g:
        config = current_app.config
        if not config.get("MYSQL_USER") or config.get("MYSQL_PASSWORD") is None:
            raise RuntimeError("Set MYSQL_USER and MYSQL_PASSWORD in the environment before using database routes.")
        g.db_connection = mysql.connector.connect(
            host=config["MYSQL_HOST"],
            port=config["MYSQL_PORT"],
            user=config["MYSQL_USER"],
            password=config["MYSQL_PASSWORD"],
            database=config["MYSQL_DATABASE"],
            charset="utf8mb4",
            autocommit=False,
        )
    return g.db_connection


def close_db(_error=None):
    connection = g.pop("db_connection", None)
    if connection is not None and connection.is_connected():
        connection.close()
