"""Reviews, conversation messages, and personal notifications."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from mysql.connector import IntegrityError

from app.db import get_db
from app.utils.auth import roles_required
from app.utils.notifications import add_notification

comms_bp = Blueprint("comms", __name__)


@comms_bp.get("/reviews/users/<int:user_id>")
def user_reviews(user_id):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT u.user_id, u.full_name, COUNT(r.review_id) AS review_count, AVG(r.rating) AS average_rating "
            "FROM `User` u LEFT JOIN Review r ON r.reviewee_id = u.user_id "
            "WHERE u.user_id = %s GROUP BY u.user_id, u.full_name",
            (user_id,),
        )
        summary = cursor.fetchone()
        if summary:
            cursor.execute(
                "SELECT r.review_id, r.contract_id, r.reviewer_id, u.full_name AS reviewer_name, "
                "r.rating, r.comment, r.created_at FROM Review r "
                "JOIN `User` u ON u.user_id = r.reviewer_id WHERE r.reviewee_id = %s "
                "ORDER BY r.created_at DESC, r.review_id DESC",
                (user_id,),
            )
            reviews = cursor.fetchall()
        else:
            reviews = []
    finally:
        cursor.close()
    if not summary:
        return _not_found("User was not found.")
    return jsonify(summary=summary, reviews=reviews), 200


@comms_bp.post("/contracts/<int:contract_id>/reviews")
@roles_required("client", "freelancer")
def create_review(contract_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"rating", "comment"} or "rating" not in body:
        return _bad_request("Provide rating and optional comment.")
    rating = body["rating"]
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        return _bad_request("rating must be a whole number from 1 to 5.")
    comment = body.get("comment")
    if comment is not None and not isinstance(comment, str):
        return _bad_request("comment must be a string or null.")

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
        if not contract:
            connection.rollback()
            return _not_found("Contract was not found.")
        reviewer_id = int(get_jwt_identity())
        role = _current_role()
        if role == "client" and contract["client_id"] == reviewer_id:
            reviewee_id = contract["freelancer_id"]
        elif role == "freelancer" and contract["freelancer_id"] == reviewer_id:
            reviewee_id = contract["client_id"]
        else:
            connection.rollback()
            return _not_found("Contract was not found.")
        if contract["status"] != "completed":
            connection.rollback()
            return _conflict("contract_incomplete", "Reviews can be submitted after the contract is completed.")
        cursor.execute(
            "INSERT INTO Review (contract_id, reviewer_id, reviewee_id, rating, comment) VALUES (%s, %s, %s, %s, %s)",
            (contract_id, reviewer_id, reviewee_id, rating, comment),
        )
        review_id = cursor.lastrowid
        add_notification(
            cursor, reviewee_id,
            f"You received a new review for contract #{contract_id} (review #{review_id}).",
            "review_received",
        )
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        if error.errno == 1062:
            return _conflict("review_exists", "You have already reviewed this contract.")
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(review_id=review_id, reviewee_id=reviewee_id), 201


@comms_bp.get("/contracts/<int:contract_id>/messages")
@roles_required("client", "freelancer")
def list_messages(contract_id):
    limit, offset = _page_args()
    if limit is None:
        return _bad_request("limit must be 1–100 and offset must be zero or greater.")
    participants, error = _contract_participants(contract_id)
    if error:
        return error
    if int(get_jwt_identity()) not in {participants["client_id"], participants["freelancer_id"]}:
        return _not_found("Contract was not found.")
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT m.message_id, m.contract_id, m.sender_id, sender.full_name AS sender_name, "
            "m.receiver_id, receiver.full_name AS receiver_name, m.body, m.sent_at, m.read_at "
            "FROM Message m JOIN `User` sender ON sender.user_id = m.sender_id "
            "JOIN `User` receiver ON receiver.user_id = m.receiver_id "
            "WHERE m.contract_id = %s ORDER BY m.sent_at, m.message_id LIMIT %s OFFSET %s",
            (contract_id, limit, offset),
        )
        messages = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(messages=messages, limit=limit, offset=offset), 200


@comms_bp.post("/contracts/<int:contract_id>/messages")
@roles_required("client", "freelancer")
def send_message(contract_id):
    body = request.get_json(silent=True)
    text = body.get("body") if isinstance(body, dict) else None
    if not isinstance(body, dict) or set(body) != {"body"} or not isinstance(text, str) or not text.strip() or len(text) > 20000:
        return _bad_request("body is required and limited to 20,000 characters.")
    participants, error = _contract_participants(contract_id)
    if error:
        return error
    identity = int(get_jwt_identity())
    if identity == participants["client_id"]:
        receiver_id = participants["freelancer_id"]
    elif identity == participants["freelancer_id"]:
        receiver_id = participants["client_id"]
    else:
        return _not_found("Contract was not found.")

    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO Message (contract_id, sender_id, receiver_id, body) VALUES (%s, %s, %s, %s)",
            (contract_id, identity, receiver_id, text.strip()),
        )
        message_id = cursor.lastrowid
        add_notification(
            cursor, receiver_id,
            f"You received a new message in contract #{contract_id} (message #{message_id}).",
            "message_received",
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(message_id=message_id, receiver_id=receiver_id), 201


@comms_bp.patch("/messages/<int:message_id>/read")
@roles_required("client", "freelancer")
def mark_message_read(message_id):
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT receiver_id FROM Message WHERE message_id = %s FOR UPDATE", (message_id,))
        message = cursor.fetchone()
        if not message or message["receiver_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Message was not found.")
        cursor.execute("UPDATE Message SET read_at = CURRENT_TIMESTAMP WHERE message_id = %s", (message_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(message_id=message_id, read=True), 200


@comms_bp.get("/notifications")
@roles_required("client", "freelancer", "admin")
def list_notifications():
    limit, offset = _page_args()
    if limit is None:
        return _bad_request("limit must be 1–100 and offset must be zero or greater.")
    unread_only = request.args.get("unread_only", "false").lower()
    if unread_only not in {"true", "false"}:
        return _bad_request("unread_only must be true or false.")
    conditions = ["user_id = %s"]
    params = [int(get_jwt_identity())]
    if unread_only == "true":
        conditions.append("is_read = FALSE")
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT notification_id, message, notification_type, is_read, created_at FROM Notification "
            f"WHERE {' AND '.join(conditions)} ORDER BY created_at DESC, notification_id DESC LIMIT %s OFFSET %s",
            (*params, limit, offset),
        )
        notifications = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(notifications=notifications, limit=limit, offset=offset), 200


@comms_bp.patch("/notifications/<int:notification_id>/read")
@roles_required("client", "freelancer", "admin")
def mark_notification_read(notification_id):
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE Notification SET is_read = TRUE WHERE notification_id = %s AND user_id = %s",
            (notification_id, int(get_jwt_identity())),
        )
        changed = cursor.rowcount
        if not changed:
            # MySQL reports changed rows by default, so marking an already-read
            # owned notification may affect zero rows. Keep this operation
            # idempotent while still hiding notifications owned by other users.
            cursor.execute(
                "SELECT 1 FROM Notification WHERE notification_id = %s AND user_id = %s",
                (notification_id, int(get_jwt_identity())),
            )
            owned = cursor.fetchone() is not None
            if not owned:
                connection.rollback()
                return _not_found("Notification was not found.")
        connection.commit()
    finally:
        cursor.close()
    return jsonify(notification_id=notification_id, is_read=True), 200


@comms_bp.patch("/notifications/read-all")
@roles_required("client", "freelancer", "admin")
def mark_all_notifications_read():
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute("UPDATE Notification SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE", (int(get_jwt_identity()),))
        changed = cursor.rowcount
        connection.commit()
    finally:
        cursor.close()
    return jsonify(updated=changed), 200


def _contract_participants(contract_id):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT c.status, p.client_id, a.freelancer_id FROM Contract c "
            "JOIN Project p ON p.project_id = c.project_id "
            "JOIN Application a ON a.application_id = c.application_id WHERE c.contract_id = %s",
            (contract_id,),
        )
        participants = cursor.fetchone()
    finally:
        cursor.close()
    if not participants:
        return None, _not_found("Contract was not found.")
    return participants, None


def _current_role():
    # The JWT role is checked against the live database role by roles_required.
    return get_jwt().get("role")


def _page_args():
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
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
