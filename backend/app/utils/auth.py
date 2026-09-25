"""Role checks for JWT-protected route handlers."""

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.db import get_db


def roles_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        @jwt_required()
        def wrapped(*args, **kwargs):
            cursor = get_db().cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT role, account_status FROM `User` WHERE user_id = %s",
                    (int(get_jwt_identity()),),
                )
                user = cursor.fetchone()
            finally:
                cursor.close()
            if not user or user["account_status"] != "active":
                return jsonify(error={"code": "account_inactive", "message": "This account is not active."}), 401
            if get_jwt().get("role") != user["role"]:
                return jsonify(error={"code": "stale_role_token", "message": "Your role changed; sign in again."}), 401
            if user["role"] not in allowed_roles:
                return jsonify(error={"code": "forbidden", "message": "Your role cannot access this resource."}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator
