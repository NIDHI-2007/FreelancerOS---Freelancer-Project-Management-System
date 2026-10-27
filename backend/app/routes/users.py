"""Self-service account details and admin user management."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from mysql.connector import IntegrityError

from app.db import get_db
from app.utils.auth import roles_required

users_bp = Blueprint("users", __name__)
USER_FIELDS = ("user_id", "email", "full_name", "role", "account_status", "created_at")
STATUSES = {"active", "suspended", "closed"}


@users_bp.get("/me")
@roles_required("client", "freelancer", "admin")
def get_me():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, email, full_name, role, account_status, created_at "
            "FROM `User` WHERE user_id = %s",
            (int(get_jwt_identity()),),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()
    if not user:
        return jsonify(error={"code": "not_found", "message": "User was not found."}), 404
    return jsonify(user=user), 200


@users_bp.patch("/me")
@roles_required("client", "freelancer", "admin")
def update_me():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body:
        return _bad_request("A non-empty JSON object is required.")
    allowed = {"email", "full_name"}
    if set(body) - allowed:
        return _bad_request("Only email and full_name can be changed here.")
    values = {}
    if "email" in body:
        if not isinstance(body["email"], str):
            return _bad_request("email must be a string.")
        email = body["email"].strip().lower()
        if not email or len(email) > 254 or "@" not in email:
            return _bad_request("Provide a valid email address.")
        values["email"] = email
    if "full_name" in body:
        if not isinstance(body["full_name"], str) or not body["full_name"].strip() or len(body["full_name"].strip()) > 150:
            return _bad_request("full_name is required and must be at most 150 characters.")
        values["full_name"] = body["full_name"].strip()

    assignments = ", ".join(f"{column} = %s" for column in values)
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"UPDATE `User` SET {assignments} WHERE user_id = %s",
            (*values.values(), int(get_jwt_identity())),
        )
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        if error.errno == 1062:
            return jsonify(error={"code": "email_already_registered", "message": "An account with this email already exists."}), 409
        raise
    finally:
        cursor.close()
    return jsonify(message="Account updated."), 200


@users_bp.get("")
@roles_required("admin")
def list_users():
    limit, offset = _parse_int(request.args.get("limit", "50")), _parse_int(request.args.get("offset", "0"))
    if limit is None or offset is None or not 1 <= limit <= 100 or offset < 0:
        return _bad_request("limit must be 1–100 and offset must be zero or greater.")
    clauses, params = [], []
    for field, values in (("role", {"client", "freelancer", "admin"}), ("status", STATUSES)):
        value = request.args.get(field)
        if value:
            value = value.strip().lower()
            if value not in values:
                return _bad_request(f"Invalid {field} filter.")
            column = "account_status" if field == "status" else field
            clauses.append(f"{column} = %s")
            params.append(value)
    search = request.args.get("q", "").strip()
    if search:
        clauses.append("(email LIKE %s OR full_name LIKE %s)")
        params.extend((f"%{search}%", f"%{search}%"))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT {', '.join(USER_FIELDS)} FROM `User`{where} ORDER BY user_id LIMIT %s OFFSET %s",
            (*params, limit, offset),
        )
        users = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(users=users, limit=limit, offset=offset), 200


@users_bp.get("/<int:user_id>")
@roles_required("admin")
def get_user(user_id):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT {', '.join(USER_FIELDS)} FROM `User` WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
    finally:
        cursor.close()
    if not user:
        return jsonify(error={"code": "not_found", "message": "User was not found."}), 404
    return jsonify(user=user), 200


@users_bp.patch("/<int:user_id>/status")
@roles_required("admin")
def update_user_status(user_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"account_status"}:
        return _bad_request("Provide account_status only.")
    status = body["account_status"]
    if not isinstance(status, str) or status not in STATUSES:
        return _bad_request("account_status must be active, suspended, or closed.")
    acting_admin = int(get_jwt_identity())
    if user_id == acting_admin and status != "active":
        return jsonify(error={"code": "self_lockout_prevented", "message": "An administrator cannot suspend or close their own account."}), 409
    cursor = get_db().cursor()
    try:
        if status != "active":
            cursor.execute(
                "SELECT COUNT(*) FROM `User` WHERE role = 'admin' AND account_status = 'active' AND user_id <> %s",
                (user_id,),
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute("SELECT role, account_status FROM `User` WHERE user_id = %s", (user_id,))
                target = cursor.fetchone()
                if target and target[0] == "admin" and target[1] == "active":
                    cursor.connection.rollback()
                    return jsonify(error={"code": "last_active_admin", "message": "The platform must retain at least one active administrator."}), 409
        cursor.execute("UPDATE `User` SET account_status = %s WHERE user_id = %s", (status, user_id))
        changed = cursor.rowcount
        cursor.connection.commit()
    finally:
        cursor.close()
    if not changed:
        return jsonify(error={"code": "not_found", "message": "User was not found or status is unchanged."}), 404
    return jsonify(message="User status updated.", user_id=user_id, account_status=status), 200


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400
