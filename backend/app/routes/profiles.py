"""Client and freelancer profile and portfolio endpoints."""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.db import get_db
from app.utils.auth import roles_required

profiles_bp = Blueprint("profiles", __name__)
CLIENT_FIELDS = {"company_name", "bio", "location", "website"}
FREELANCER_FIELDS = {"headline", "bio", "hourly_rate", "experience_years", "location", "availability_status"}
AVAILABILITY = {"available", "busy", "unavailable"}


@profiles_bp.get("/clients/me")
@roles_required("client")
def get_client_profile():
    return _get_profile("Client", int(get_jwt_identity()), CLIENT_FIELDS)


@profiles_bp.patch("/clients/me")
@roles_required("client")
def update_client_profile():
    body = request.get_json(silent=True)
    error = _validate_profile_body(body, CLIENT_FIELDS)
    if error:
        return error
    error = _validate_text_fields(
        body,
        {"company_name": 160, "location": 120, "website": 255},
        nullable={"company_name", "bio", "location", "website"},
    )
    if error:
        return error
    return _update_profile("Client", int(get_jwt_identity()), body)


@profiles_bp.get("/freelancers/me")
@roles_required("freelancer")
def get_freelancer_profile():
    return _get_profile("Freelancer", int(get_jwt_identity()), FREELANCER_FIELDS)


@profiles_bp.patch("/freelancers/me")
@roles_required("freelancer")
def update_freelancer_profile():
    body = request.get_json(silent=True)
    error = _validate_profile_body(body, FREELANCER_FIELDS)
    if error:
        return error
    error = _validate_text_fields(
        body,
        {"headline": 180, "location": 120},
        nullable={"headline", "bio", "location"},
    )
    if error:
        return error
    if "hourly_rate" in body:
        try:
            rate = Decimal(str(body["hourly_rate"]))
            if not rate.is_finite() or rate < 0 or rate > Decimal("9999999999.99"):
                raise InvalidOperation
            body["hourly_rate"] = rate
        except (InvalidOperation, TypeError, ValueError):
            return _bad_request("hourly_rate must be a number between 0 and 9999999999.99.")
    if "experience_years" in body:
        years = body["experience_years"]
        if isinstance(years, bool) or not isinstance(years, int) or not 0 <= years <= 65535:
            return _bad_request("experience_years must be a whole number between 0 and 65535.")
    if "availability_status" in body and (
        not isinstance(body["availability_status"], str) or body["availability_status"] not in AVAILABILITY
    ):
        return _bad_request("availability_status must be available, busy, or unavailable.")
    return _update_profile("Freelancer", int(get_jwt_identity()), body)


@profiles_bp.get("/freelancers/me/portfolio")
@roles_required("freelancer")
def list_portfolio():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT portfolio_id, title, description, project_url, created_at "
            "FROM Portfolio WHERE freelancer_id = %s ORDER BY created_at DESC, portfolio_id DESC",
            (int(get_jwt_identity()),),
        )
        items = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(portfolio=items), 200


@profiles_bp.post("/freelancers/me/portfolio")
@roles_required("freelancer")
def create_portfolio_item():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("title"), str) or not body["title"].strip():
        return _bad_request("title is required.")
    allowed = {"title", "description", "project_url"}
    if set(body) - allowed or len(body["title"].strip()) > 180:
        return _bad_request("Only title, description, and project_url are accepted; title is limited to 180 characters.")
    for key in ("description", "project_url"):
        if key in body and body[key] is not None and not isinstance(body[key], str):
            return _bad_request(f"{key} must be a string or null.")
    if body.get("project_url") is not None and len(body["project_url"]) > 2048:
        return _bad_request("project_url is limited to 2048 characters.")
    cursor = get_db().cursor()
    try:
        cursor.execute(
            "INSERT INTO Portfolio (freelancer_id, title, description, project_url) VALUES (%s, %s, %s, %s)",
            (int(get_jwt_identity()), body["title"].strip(), body.get("description"), body.get("project_url")),
        )
        item_id = cursor.lastrowid
        cursor.connection.commit()
    finally:
        cursor.close()
    return jsonify(portfolio_id=item_id), 201


@profiles_bp.patch("/freelancers/me/portfolio/<int:item_id>")
@roles_required("freelancer")
def update_portfolio_item(item_id):
    body = request.get_json(silent=True)
    allowed = {"title", "description", "project_url"}
    if not isinstance(body, dict) or not body or set(body) - allowed:
        return _bad_request("Provide one or more of title, description, or project_url.")
    if "title" in body and (not isinstance(body["title"], str) or not body["title"].strip() or len(body["title"].strip()) > 180):
        return _bad_request("title is required and limited to 180 characters.")
    if "description" in body and body["description"] is not None and not isinstance(body["description"], str):
        return _bad_request("description must be a string or null.")
    if "project_url" in body and body["project_url"] is not None and (not isinstance(body["project_url"], str) or len(body["project_url"]) > 2048):
        return _bad_request("project_url must be a string of at most 2048 characters or null.")
    assignments = ", ".join(f"{key} = %s" for key in body)
    cursor = get_db().cursor()
    try:
        cursor.execute(
            f"UPDATE Portfolio SET {assignments} WHERE portfolio_id = %s AND freelancer_id = %s",
            (*[body[key].strip() if key == "title" else body[key] for key in body], item_id, int(get_jwt_identity())),
        )
        changed = cursor.rowcount
        cursor.connection.commit()
    finally:
        cursor.close()
    if not changed:
        return jsonify(error={"code": "not_found", "message": "Portfolio item was not found or no values changed."}), 404
    return jsonify(message="Portfolio item updated."), 200


@profiles_bp.delete("/freelancers/me/portfolio/<int:item_id>")
@roles_required("freelancer")
def delete_portfolio_item(item_id):
    cursor = get_db().cursor()
    try:
        cursor.execute(
            "DELETE FROM Portfolio WHERE portfolio_id = %s AND freelancer_id = %s",
            (item_id, int(get_jwt_identity())),
        )
        deleted = cursor.rowcount
        cursor.connection.commit()
    finally:
        cursor.close()
    if not deleted:
        return jsonify(error={"code": "not_found", "message": "Portfolio item was not found."}), 404
    return jsonify(message="Portfolio item deleted."), 200


def _get_profile(table, user_id, fields):
    columns = ", ".join(sorted(fields))
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT user_id, {columns} FROM {table} WHERE user_id = %s", (user_id,))
        profile = cursor.fetchone()
    finally:
        cursor.close()
    if not profile:
        return jsonify(error={"code": "not_found", "message": "Profile was not found."}), 404
    return jsonify(profile=profile), 200


def _update_profile(table, user_id, body):
    assignments = ", ".join(f"{key} = %s" for key in body)
    cursor = get_db().cursor()
    try:
        cursor.execute(
            f"UPDATE {table} SET {assignments} WHERE user_id = %s",
            (*[body[key] for key in body], user_id),
        )
        cursor.connection.commit()
    finally:
        cursor.close()
    return jsonify(message="Profile updated."), 200


def _validate_profile_body(body, allowed):
    if not isinstance(body, dict) or not body:
        return _bad_request("A non-empty JSON object is required.")
    if set(body) - allowed:
        return _bad_request("One or more fields are not editable on this profile.")
    return None


def _validate_text_fields(body, limits, nullable):
    for key in set(body) & (set(limits) | {"bio"}):
        value = body[key]
        if value is None and key in nullable:
            continue
        if not isinstance(value, str):
            return _bad_request(f"{key} must be a string" + (" or null." if key in nullable else "."))
        limit = limits.get(key)
        if limit is not None and len(value) > limit:
            return _bad_request(f"{key} must be at most {limit} characters.")
    return None


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400
