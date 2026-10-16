"""JWT authentication and account registration endpoints."""

from datetime import datetime, timezone
import re

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from mysql.connector import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db
auth_bp = Blueprint("auth", __name__)
SELF_REGISTERABLE_ROLES = {"client", "freelancer"}


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400


@auth_bp.post("/register")
def register():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _bad_request("A JSON object is required.")

    email = body.get("email", "")
    full_name = body.get("full_name", "")
    password = body.get("password", "")
    role = body.get("role", "")
    if not all(isinstance(value, str) for value in (email, full_name, password, role)):
        return _bad_request("email, full_name, password, and role must be strings.")

    email, full_name, role = email.strip().lower(), full_name.strip(), role.strip().lower()
    if not email or len(email) > 254 or "@" not in email:
        return _bad_request("Provide a valid email address.")
    if not full_name or len(full_name) > 150:
        return _bad_request("full_name is required and must be at most 150 characters.")
    if len(password) < 8:
        return _bad_request("password must contain at least 8 characters.")
    if role not in SELF_REGISTERABLE_ROLES:
        return _bad_request("role must be client or freelancer.")

    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO `User` (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
            (email, generate_password_hash(password), full_name, role),
        )
        user_id = cursor.lastrowid
        profile_table = "Client" if role == "client" else "Freelancer"
        cursor.execute(f"INSERT INTO {profile_table} (user_id) VALUES (%s)", (user_id,))
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        if error.errno == 1062:
            return jsonify(error={"code": "email_already_registered", "message": "An account with this email already exists."}), 409
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()

    return jsonify(user={"user_id": user_id, "email": email, "full_name": full_name, "role": role}), 201


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _bad_request("A JSON object is required.")
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return _bad_request("email and password are required.")

    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, email, full_name, role, account_status, password_hash "
            "FROM `User` WHERE email = %s",
            (email.strip().lower(),),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()

    if not user or not check_password_hash(user["password_hash"], password) or user["account_status"] != "active":
        return jsonify(error={"code": "invalid_credentials", "message": "Email or password is incorrect."}), 401

    token = create_access_token(
        identity=str(user["user_id"]),
        additional_claims={"role": user["role"]},
    )
    return jsonify(
        access_token=token,
        user={"user_id": user["user_id"], "email": user["email"], "full_name": user["full_name"], "role": user["role"]},
    ), 200


@auth_bp.post("/forgot-password")
def forgot_password():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _bad_request("A JSON object is required.")
    email = body.get("email")
    # Accept the former `password` field for compatibility while preferring
    # the explicit request name used by the current UI.
    password = body.get("new_password", body.get("password"))
    if (
        not isinstance(email, str)
        or len(email.strip()) > 254
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip())
    ):
        return _bad_request("Provide a valid email address.")
    if not isinstance(password, str) or len(password) < 8:
        return _bad_request("new_password must contain at least 8 characters.")
    if not current_app.config.get("PASSWORD_RESET_DEV_MODE") or request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify(error={"code": "password_reset_unavailable", "message": "Password recovery is available only in local development."}), 403

    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE `User` SET password_hash = %s "
            "WHERE email = %s AND account_status = 'active'",
            (generate_password_hash(password), email.strip().lower()),
        )
        updated = cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    if not updated:
        return jsonify(error={"code": "password_reset_failed", "message": "Unable to reset the password. Check the email and try again."}), 400
    return jsonify(message="Password reset successfully. Please log in."), 200


@auth_bp.post("/logout")
@jwt_required(skip_revocation_check=True)
def logout():
    claims = get_jwt()
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM Revoked_Token WHERE expires_at <= UTC_TIMESTAMP()")
        # Make logout safe to retry if the response is lost after the DB commit.
        cursor.execute("SELECT 1 FROM Revoked_Token WHERE token_jti = %s", (claims["jti"],))
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO Revoked_Token (token_jti, expires_at) VALUES (%s, %s)",
                (claims["jti"], datetime.fromtimestamp(claims["exp"], timezone.utc).replace(tzinfo=None)),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(message="Logged out."), 200


@auth_bp.get("/me")
@jwt_required()
def current_user():
    claims = get_jwt()
    return jsonify(user_id=get_jwt_identity(), role=claims.get("role")), 200
