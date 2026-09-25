"""JWT authentication and account registration endpoints."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from mysql.connector import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db
from app.utils.email import send_password_reset_email, smtp_is_configured

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
    if not isinstance(email, str) or not email.strip() or len(email.strip()) > 254 or "@" not in email:
        return _bad_request("Provide a valid email address.")

    response = jsonify(message="If an account matches that email, reset instructions will be sent.")
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, email FROM `User` WHERE email = %s AND account_status = 'active'",
            (email.strip().lower(),),
        )
        user = cursor.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                minutes=current_app.config["PASSWORD_RESET_TOKEN_MINUTES"]
            )
            cursor.execute(
                "UPDATE Password_Reset_Token SET used_at = UTC_TIMESTAMP() "
                "WHERE user_id = %s AND used_at IS NULL",
                (user["user_id"],),
            )
            cursor.execute(
                "DELETE FROM Password_Reset_Token WHERE expires_at <= UTC_TIMESTAMP()",
            )
            cursor.execute(
                "INSERT INTO Password_Reset_Token (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user["user_id"], token_hash, expires_at),
            )
            connection.commit()
            # Put the credential in the URL fragment so it is not sent in the
            # initial HTTP request or written to normal access logs.
            reset_url = (
                f"{current_app.config['APP_BASE_URL']}/#"
                f"{urlencode({'reset_token': token})}"
            )
            local_request = request.remote_addr in {"127.0.0.1", "::1"}
            dev_mail_fallback = (
                current_app.config.get("PASSWORD_RESET_DEV_MODE")
                and local_request
                and not smtp_is_configured()
            )
            if dev_mail_fallback:
                current_app.logger.warning(
                    "DEV ONLY: password reset link for local testing: %s", reset_url
                )
            else:
                try:
                    send_password_reset_email(user["email"], reset_url)
                except Exception as error:
                    current_app.logger.error(
                        "Password reset email delivery failed (%s).", type(error).__name__
                    )
                    cursor.execute(
                        "UPDATE Password_Reset_Token SET used_at = UTC_TIMESTAMP() "
                        "WHERE token_hash = %s AND used_at IS NULL",
                        (token_hash,),
                    )
                    connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    response.status_code = 202
    return response


@auth_bp.post("/reset-password")
def reset_password():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _bad_request("A JSON object is required.")
    token, password = body.get("token"), body.get("password")
    if not isinstance(token, str) or not token or not isinstance(password, str):
        return _bad_request("token and password are required.")
    if len(password) < 8:
        return _bad_request("password must contain at least 8 characters.")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT reset_token_id, user_id FROM Password_Reset_Token "
            "WHERE token_hash = %s AND used_at IS NULL AND expires_at > UTC_TIMESTAMP() FOR UPDATE",
            (token_hash,),
        )
        reset_record = cursor.fetchone()
        if not reset_record:
            connection.rollback()
            return jsonify(error={"code": "invalid_reset_token", "message": "The reset link is invalid or expired."}), 400

        cursor.execute(
            "UPDATE `User` SET password_hash = %s WHERE user_id = %s AND account_status = 'active'",
            (generate_password_hash(password), reset_record["user_id"]),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return jsonify(error={"code": "invalid_reset_token", "message": "The reset link is invalid or expired."}), 400
        cursor.execute(
            "UPDATE Password_Reset_Token SET used_at = UTC_TIMESTAMP() "
            "WHERE user_id = %s AND used_at IS NULL",
            (reset_record["user_id"],),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(message="Password reset. You can now sign in with your new password."), 200


@auth_bp.post("/logout")
@jwt_required()
def logout():
    claims = get_jwt()
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM Revoked_Token WHERE expires_at <= UTC_TIMESTAMP()")
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
