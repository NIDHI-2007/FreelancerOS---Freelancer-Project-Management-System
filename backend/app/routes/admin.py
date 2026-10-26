"""Platform reports and participant/admin dispute workflows."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.db import get_db
from app.utils.auth import roles_required
from app.utils.notifications import add_notification

admin_bp = Blueprint("admin", __name__)
DISPUTE_STATUSES = {"open", "investigating", "resolved", "closed"}
DISPUTE_SELECT = (
    "SELECT d.dispute_id, d.contract_id, d.opened_by, opener.full_name AS opener_name, "
    "d.reason, d.description, d.status, d.admin_id, admin_user.full_name AS admin_name, "
    "d.resolution, d.created_at, d.resolved_at, p.title AS project_title, "
    "p.client_id, a.freelancer_id, client_user.full_name AS client_name, "
    "freelancer_user.full_name AS freelancer_name "
    "FROM Dispute d JOIN `User` opener ON opener.user_id = d.opened_by "
    "LEFT JOIN `User` admin_user ON admin_user.user_id = d.admin_id "
    "JOIN Contract c ON c.contract_id = d.contract_id "
    "JOIN Project p ON p.project_id = c.project_id "
    "JOIN Application a ON a.application_id = c.application_id "
    "JOIN `User` client_user ON client_user.user_id = p.client_id "
    "JOIN `User` freelancer_user ON freelancer_user.user_id = a.freelancer_id"
)


@admin_bp.get("/admin/reports/summary")
@roles_required("admin")
def report_summary():
    cursor = get_db().cursor(dictionary=True)
    try:
        report = {}
        for name, query in {
            "users_by_role": "SELECT role AS label, COUNT(*) AS count FROM `User` GROUP BY role ORDER BY role",
            "users_by_status": "SELECT account_status AS label, COUNT(*) AS count FROM `User` GROUP BY account_status ORDER BY account_status",
            "projects_by_status": "SELECT status AS label, COUNT(*) AS count FROM Project GROUP BY status ORDER BY status",
            "applications_by_status": "SELECT status AS label, COUNT(*) AS count FROM Application GROUP BY status ORDER BY status",
            "contracts_by_status": "SELECT status AS label, COUNT(*) AS count FROM Contract GROUP BY status ORDER BY status",
            "payments_by_status": "SELECT status AS label, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount FROM Payment GROUP BY status ORDER BY status",
            "disputes_by_status": "SELECT status AS label, COUNT(*) AS count FROM Dispute GROUP BY status ORDER BY status",
            "reviews_by_role": "SELECT u.role AS label, COUNT(r.review_id) AS count, AVG(r.rating) AS average_rating FROM `User` u LEFT JOIN Review r ON r.reviewee_id = u.user_id GROUP BY u.role ORDER BY u.role",
        }.items():
            cursor.execute(query)
            report[name] = cursor.fetchall()
        cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM Payment WHERE status = 'completed'")
        report["completed_payment_volume"] = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM Project")
        report["project_count"] = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM `User`")
        report["user_count"] = cursor.fetchone()["total"]
    finally:
        cursor.close()
    return jsonify(report=report), 200


@admin_bp.get("/admin/reports/earnings")
@roles_required("admin")
def report_earnings():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute("SELECT freelancer_id, full_name, total_earnings, completed_payment_count FROM v_freelancer_earnings ORDER BY total_earnings DESC, freelancer_id LIMIT 100")
        earnings = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(earnings=earnings), 200


@admin_bp.get("/admin/reports/spending")
@roles_required("admin")
def report_spending():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute("SELECT client_id, full_name, total_spending, completed_payment_count FROM v_client_spending ORDER BY total_spending DESC, client_id LIMIT 100")
        spending = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(spending=spending), 200


@admin_bp.get("/admin/disputes")
@roles_required("admin")
def list_disputes():
    status = request.args.get("status")
    if status and status not in DISPUTE_STATUSES:
        return _bad_request("status must be open, investigating, resolved, or closed.")
    limit, offset = _pagination()
    if limit is None:
        return _bad_request("limit must be 1–100 and offset must be zero or greater.")
    where = " WHERE d.status = %s" if status else ""
    params = (status, limit, offset) if status else (limit, offset)
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(f"{DISPUTE_SELECT}{where} ORDER BY d.created_at DESC, d.dispute_id DESC LIMIT %s OFFSET %s", params)
        disputes = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(disputes=disputes, limit=limit, offset=offset), 200


@admin_bp.get("/disputes/mine")
@roles_required("client", "freelancer")
def my_disputes():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            f"{DISPUTE_SELECT} WHERE d.opened_by = %s OR p.client_id = %s OR a.freelancer_id = %s "
            "ORDER BY d.created_at DESC, d.dispute_id DESC LIMIT 100",
            (int(get_jwt_identity()),) * 3,
        )
        disputes = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(disputes=disputes), 200


@admin_bp.post("/contracts/<int:contract_id>/disputes")
@roles_required("client", "freelancer")
def create_dispute(contract_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"reason", "description"}:
        return _bad_request("Provide reason and optional description only.")
    reason, description = body.get("reason"), body.get("description")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 180:
        return _bad_request("reason is required and limited to 180 characters.")
    if description is not None and (not isinstance(description, str) or len(description) > 20000):
        return _bad_request("description must be a string of at most 20,000 characters or null.")

    user_id = int(get_jwt_identity())
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT c.status, p.client_id, a.freelancer_id FROM Contract c "
            "JOIN Project p ON p.project_id = c.project_id "
            "JOIN Application a ON a.application_id = c.application_id "
            "WHERE c.contract_id = %s FOR UPDATE",
            (contract_id,),
        )
        contract = cursor.fetchone()
        if not contract or user_id not in {contract["client_id"], contract["freelancer_id"]}:
            connection.rollback()
            return _not_found("Contract was not found.")
        if contract["status"] == "cancelled":
            connection.rollback()
            return _conflict("contract_cancelled", "A dispute cannot be opened on a cancelled contract.")
        cursor.execute(
            "INSERT INTO Dispute (contract_id, opened_by, reason, description) VALUES (%s, %s, %s, %s)",
            (contract_id, user_id, reason.strip(), description.strip() if description else None),
        )
        dispute_id = cursor.lastrowid
        other_party = contract["freelancer_id"] if user_id == contract["client_id"] else contract["client_id"]
        add_notification(
            cursor, other_party,
            f"Dispute #{dispute_id} was opened for contract #{contract_id}.",
            "dispute_opened",
        )
        cursor.execute(
            "SELECT user_id FROM `User` WHERE role = 'admin' AND account_status = 'active' "
            "ORDER BY user_id LIMIT 1"
        )
        primary_admin = cursor.fetchone()
        if primary_admin:
            add_notification(
                cursor, primary_admin["user_id"],
                f"Dispute #{dispute_id} requires review.", "dispute_opened",
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(dispute_id=dispute_id, contract_id=contract_id, status="open"), 201


@admin_bp.patch("/admin/disputes/<int:dispute_id>")
@roles_required("admin")
def update_dispute(dispute_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"status", "resolution"} or "status" not in body:
        return _bad_request("Provide status and optional resolution only.")
    status, resolution = body["status"], body.get("resolution")
    if not isinstance(status, str) or status not in DISPUTE_STATUSES - {"open"}:
        return _bad_request("status must be investigating, resolved, or closed.")
    if resolution is not None and (not isinstance(resolution, str) or len(resolution) > 20000):
        return _bad_request("resolution must be a string of at most 20,000 characters or null.")
    if status in {"resolved", "closed"} and (not isinstance(resolution, str) or not resolution.strip()):
        return _bad_request("A resolution is required when resolving or closing a dispute.")

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT d.status, d.contract_id, d.opened_by, p.client_id, a.freelancer_id "
            f"FROM Dispute d JOIN Contract c ON c.contract_id = d.contract_id "
            f"JOIN Project p ON p.project_id = c.project_id "
            f"JOIN Application a ON a.application_id = c.application_id "
            f"WHERE d.dispute_id = %s FOR UPDATE",
            (dispute_id,),
        )
        dispute = cursor.fetchone()
        if not dispute:
            connection.rollback()
            return _not_found("Dispute was not found.")
        transitions = {"open": {"investigating", "resolved", "closed"}, "investigating": {"resolved", "closed"}, "resolved": {"closed"}, "closed": set()}
        if status not in transitions[dispute["status"]]:
            connection.rollback()
            return _conflict("invalid_dispute_transition", f"A dispute cannot move from {dispute['status']} to {status}.")
        cursor.execute(
            "UPDATE Dispute SET status = %s, admin_id = %s, "
            "resolution = COALESCE(%s, resolution), "
            "resolved_at = CASE WHEN %s IN ('resolved','closed') THEN CURRENT_TIMESTAMP ELSE resolved_at END "
            "WHERE dispute_id = %s",
            (status, int(get_jwt_identity()), resolution.strip() if resolution else None, status, dispute_id),
        )
        notice_type = "dispute_resolved" if status == "resolved" else "dispute_status"
        message = (
            f"Dispute #{dispute_id} was resolved by an administrator."
            if status == "resolved"
            else f"Dispute #{dispute_id} is now {status}."
        )
        for participant_id in {dispute["client_id"], dispute["freelancer_id"]}:
            add_notification(cursor, participant_id, message, notice_type)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(dispute_id=dispute_id, status=status), 200


def _pagination():
    try:
        limit, offset = int(request.args.get("limit", "50")), int(request.args.get("offset", "0"))
    except (TypeError, ValueError):
        return None, None
    if not 1 <= limit <= 100 or offset < 0:
        return None, None
    return limit, offset


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400


def _not_found(message):
    return jsonify(error={"code": "not_found", "message": message}), 404


def _conflict(code, message):
    return jsonify(error={"code": code, "message": message}), 409
