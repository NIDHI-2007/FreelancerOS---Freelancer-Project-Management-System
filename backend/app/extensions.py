"""Flask extensions are instantiated here and initialized by the app factory."""

from flask_jwt_extended import JWTManager

jwt = JWTManager()
