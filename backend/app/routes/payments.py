"""Payment ledger and milestone settlement workflow."""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from mysql.connector import IntegrityError

from app.db import get_db
from app.utils.auth import roles_required
from app.utils.notifications import add_notification

payments_bp = Blueprint("payments", __name__)
PAYMENT_SELECT = (
    "SELECT p.payment_id, p.contract_id, p.milestone_id, p.payer_id, payer.full_name AS payer_name, "
    "p.payee_id, payee.full_name AS payee_name, p.amount, p.status, p.payment_method, "
    "p.transaction_reference, p.paid_at, p.created_at "
    "FROM Payment p JOIN `User` payer ON payer.user_id = p.payer_id "
    "JOIN `User` payee ON payee.user_id = p.payee_id"
)
ACTIVE_PAYMENT_STATUSES = ("pending", "processing", "completed")


@payments_bp.get("/payments/mine")
@roles_required("client", "freelancer", "admin")
def list_my_payments():
    identity = int(get_jwt_identity())
    role = get_jwt().get("role")
    cursor = get_db().cursor(dictionary=True)
    try:
        if role == "admin":
            cursor.execute(f"{PAYMENT_SELECT} ORDER BY p.created_at DESC, p.payment_id DESC")
        else:
            party_column = "p.payer_id" if role == "client" else "p.payee_id"
            cursor.execute(f"{PAYMENT_SELECT} WHERE {party_column} = %s ORDER BY p.created_at DESC, p.payment_id DESC", (identity,))
        payments = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(payments=payments), 200


@payments_bp.get("/payments/<int:payment_id>")
@roles_required("client", "freelancer", "admin")
def get_payment(payment_id):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(f"{PAYMENT_SELECT} WHERE p.payment_id = %s", (payment_id,))
        payment = cursor.fetchone()
    finally:
        cursor.close()
    if not payment:
        return _not_found("Payment was not found.")
    if get_jwt().get("role") != "admin" and int(get_jwt_identity()) not in {payment["payer_id"], payment["payee_id"]}:
        return _not_found("Payment was not found.")
    return jsonify(payment=payment), 200


@payments_bp.post("/contracts/<int:contract_id>/payments")
@roles_required("client")
def create_payment(contract_id):
    body = request.get_json(silent=True)
    allowed = {"amount", "milestone_id", "payment_method"}
    if not isinstance(body, dict) or set(body) - allowed or "amount" not in body:
        return _bad_request("Provide amount and optional milestone_id and payment_method.")
    try:
        amount = Decimal(str(body["amount"]))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99"):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        return _bad_request("amount must be positive and no greater than 9999999999.99.")
    milestone_id = body.get("milestone_id")
    if milestone_id is not None and (isinstance(milestone_id, bool) or not isinstance(milestone_id, int) or milestone_id < 1):
        return _bad_request("milestone_id must be a positive integer or null.")
    payment_method = body.get("payment_method")
    if payment_method is not None and (not isinstance(payment_method, str) or len(payment_method) > 40):
        return _bad_request("payment_method must be a string of at most 40 characters or null.")

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT c.status, p.client_id, a.freelancer_id, c.agreed_amount "
            "FROM Contract c JOIN Project p ON p.project_id = c.project_id "
            "JOIN Application a ON a.application_id = c.application_id "
            "WHERE c.contract_id = %s FOR UPDATE",
            (contract_id,),
        )
        contract = cursor.fetchone()
        if not contract or contract["client_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Contract was not found.")
        if contract["status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Payments can only be initiated for active contracts.")

        if milestone_id is not None:
            cursor.execute(
                "SELECT amount, status FROM Milestone WHERE milestone_id = %s AND contract_id = %s FOR UPDATE",
                (milestone_id, contract_id),
            )
            milestone = cursor.fetchone()
            if not milestone:
                connection.rollback()
                return _not_found("Milestone was not found for this contract.")
            if milestone["status"] != "approved":
                connection.rollback()
                return _conflict("milestone_not_approved", "Only approved milestones can be paid.")
            cursor.execute(
                "SELECT amount FROM Payment WHERE milestone_id = %s "
                "AND status IN ('pending','processing','completed') FOR UPDATE",
                (milestone_id,),
            )
            reserved = sum((Decimal(str(row["amount"])) for row in cursor.fetchall()), Decimal("0"))
            if reserved + amount > Decimal(str(milestone["amount"])):
                connection.rollback()
                return _conflict("milestone_amount_exceeded", "Payments cannot exceed the approved milestone amount.")
        else:
            cursor.execute(
                "SELECT amount FROM Payment WHERE contract_id = %s "
                "AND status IN ('pending','processing','completed') FOR UPDATE",
                (contract_id,),
            )
            reserved = sum((Decimal(str(row["amount"])) for row in cursor.fetchall()), Decimal("0"))
            if reserved + amount > Decimal(str(contract["agreed_amount"])):
                connection.rollback()
                return _conflict("contract_amount_exceeded", "Payments cannot exceed the contract amount.")

        cursor.execute(
            "INSERT INTO Payment (contract_id, milestone_id, payer_id, payee_id, amount, payment_method) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (contract_id, milestone_id, contract["client_id"], contract["freelancer_id"], amount, payment_method),
        )
        payment_id = cursor.lastrowid
        add_notification(cursor, contract["freelancer_id"], "A payment has been initiated for your contract.", "payment_pending")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(payment_id=payment_id, status="pending"), 201


@payments_bp.patch("/payments/<int:payment_id>/status")
@roles_required("admin")
def update_payment_status(payment_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"status", "transaction_reference"} or "status" not in body:
        return _bad_request("Provide status and optional transaction_reference.")
    status = body["status"]
    if not isinstance(status, str) or status not in {"processing", "completed", "failed", "refunded"}:
        return _bad_request("status must be processing, completed, failed, or refunded.")
    reference = body.get("transaction_reference")
    if reference is not None and (not isinstance(reference, str) or not reference.strip() or len(reference.strip()) > 120):
        return _bad_request("transaction_reference must be a non-empty string of at most 120 characters or null.")

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT contract_id, milestone_id FROM Payment WHERE payment_id = %s", (payment_id,))
        payment_link = cursor.fetchone()
        if not payment_link:
            connection.rollback()
            return _not_found("Payment was not found.")
        cursor.execute("SELECT contract_id FROM Contract WHERE contract_id = %s FOR UPDATE", (payment_link["contract_id"],))
        if not cursor.fetchone():
            connection.rollback()
            return _not_found("Contract was not found.")
        if payment_link["milestone_id"] is not None:
            cursor.execute(
                "SELECT milestone_id FROM Milestone WHERE milestone_id = %s AND contract_id = %s FOR UPDATE",
                (payment_link["milestone_id"], payment_link["contract_id"]),
            )
            if not cursor.fetchone():
                connection.rollback()
                return _not_found("Milestone was not found.")
        cursor.execute("SELECT * FROM Payment WHERE payment_id = %s FOR UPDATE", (payment_id,))
        payment = cursor.fetchone()
        if not payment:
            connection.rollback()
            return _not_found("Payment was not found.")
        transitions = {
            "pending": {"processing", "completed", "failed"},
            "processing": {"completed", "failed"},
            "completed": {"refunded"},
        }
        if status not in transitions.get(payment["status"], set()):
            connection.rollback()
            return _conflict("invalid_payment_transition", f"Payment cannot move from {payment['status']} to {status}.")
        if status == "completed" and not reference and not payment["transaction_reference"]:
            connection.rollback()
            return _bad_request("transaction_reference is required when completing a payment.")
        cursor.execute(
            "UPDATE Payment SET status = %s, transaction_reference = COALESCE(%s, transaction_reference), "
            "paid_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE paid_at END "
            "WHERE payment_id = %s",
            (status, reference.strip() if reference else None, status, payment_id),
        )
        if payment["milestone_id"] is not None and status in {"completed", "refunded"}:
            cursor.execute(
                "SELECT amount, status FROM Milestone WHERE milestone_id = %s AND contract_id = %s FOR UPDATE",
                (payment["milestone_id"], payment["contract_id"]),
            )
            milestone = cursor.fetchone()
            cursor.execute(
                "SELECT amount FROM Payment WHERE milestone_id = %s AND status = 'completed' FOR UPDATE",
                (payment["milestone_id"],),
            )
            settled = sum((Decimal(str(row["amount"])) for row in cursor.fetchall()), Decimal("0"))
            if settled >= Decimal(str(milestone["amount"])):
                cursor.execute("UPDATE Milestone SET status = 'paid' WHERE milestone_id = %s", (payment["milestone_id"],))
            elif milestone["status"] == "paid":
                cursor.execute("UPDATE Milestone SET status = 'approved' WHERE milestone_id = %s", (payment["milestone_id"],))
        add_notification(
            cursor,
            payment["payee_id"],
            f"A payment is now {status}.",
            f"payment_{status}",
        )
        add_notification(
            cursor,
            payment["payer_id"],
            f"Your payment is now {status}.",
            f"payment_{status}",
        )
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        if error.errno == 1062:
            return _conflict("duplicate_transaction_reference", "That transaction reference is already recorded.")
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(payment_id=payment_id, status=status), 200


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400


def _not_found(message):
    return jsonify(error={"code": "not_found", "message": message}), 404


def _conflict(code, message):
    return jsonify(error={"code": code, "message": message}), 409
