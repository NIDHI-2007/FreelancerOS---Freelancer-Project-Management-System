"""Contracts, task execution, and milestone review workflow."""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity

from app.db import get_db
from app.utils.auth import roles_required
from app.utils.notifications import add_notification

execution_bp = Blueprint("execution", __name__)
CONTRACT_SELECT = (
    "SELECT c.contract_id, c.project_id, c.application_id, c.start_date, c.end_date, "
    "c.agreed_amount, c.status, c.created_at, p.title AS project_title, p.client_id, "
    "a.freelancer_id FROM Contract c JOIN Project p ON p.project_id = c.project_id "
    "JOIN Application a ON a.application_id = c.application_id"
)


@execution_bp.get("/contracts/mine")
@roles_required("client", "freelancer", "admin")
def list_my_contracts():
    identity = int(get_jwt_identity())
    role = get_jwt().get("role")
    cursor = get_db().cursor(dictionary=True)
    try:
        if role == "admin":
            cursor.execute(f"{CONTRACT_SELECT} ORDER BY c.created_at DESC, c.contract_id DESC")
        else:
            participant_column = "p.client_id" if role == "client" else "a.freelancer_id"
            cursor.execute(
                f"{CONTRACT_SELECT} WHERE {participant_column} = %s ORDER BY c.created_at DESC, c.contract_id DESC",
                (identity,),
            )
        contracts = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(contracts=contracts), 200


@execution_bp.get("/contracts/<int:contract_id>")
@roles_required("client", "freelancer", "admin")
def get_contract(contract_id):
    role = get_jwt().get("role")
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(f"{CONTRACT_SELECT} WHERE c.contract_id = %s", (contract_id,))
        contract = cursor.fetchone()
    finally:
        cursor.close()
    if not contract:
        return _not_found("Contract was not found.")
    identity = int(get_jwt_identity())
    if role != "admin" and identity not in {contract["client_id"], contract["freelancer_id"]}:
        return _not_found("Contract was not found.")
    return jsonify(contract=contract), 200


@execution_bp.post("/contracts/<int:contract_id>/complete")
@roles_required("client")
def complete_contract(contract_id):
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        contract, error = _select_contract(cursor, contract_id, lock=True)
        if error:
            connection.rollback()
            return error
        if contract["client_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Contract was not found.")
        if contract["status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Only active contracts can be completed.")
        cursor.execute(
            "SELECT COUNT(*) AS open_tasks FROM Task WHERE contract_id = %s AND status NOT IN ('completed','cancelled')",
            (contract_id,),
        )
        if cursor.fetchone()["open_tasks"]:
            connection.rollback()
            return _conflict("tasks_incomplete", "Complete or cancel all tasks before completing the contract.")
        cursor.execute(
            "SELECT COUNT(*) AS open_milestones FROM Milestone WHERE contract_id = %s AND status <> 'paid'",
            (contract_id,),
        )
        if cursor.fetchone()["open_milestones"]:
            connection.rollback()
            return _conflict("milestones_incomplete", "Pay all milestones before completing the contract.")
        cursor.execute(
            "SELECT COUNT(*) AS pending_payments FROM Payment "
            "WHERE contract_id = %s AND status IN ('pending','processing')",
            (contract_id,),
        )
        if cursor.fetchone()["pending_payments"]:
            connection.rollback()
            return _conflict("payments_pending", "Settle or fail pending payments before completing the contract.")
        cursor.execute("SELECT amount FROM Payment WHERE contract_id = %s AND status = 'completed' FOR UPDATE", (contract_id,))
        paid_total = sum((Decimal(str(row["amount"])) for row in cursor.fetchall()), Decimal("0"))
        if paid_total < Decimal(str(contract["agreed_amount"])):
            connection.rollback()
            return _conflict("balance_remaining", "Settle the full contract amount before completing it.")
        cursor.execute("UPDATE Contract SET status = 'completed' WHERE contract_id = %s", (contract_id,))
        cursor.execute("UPDATE Project SET status = 'completed' WHERE project_id = %s", (contract["project_id"],))
        add_notification(cursor, contract["freelancer_id"], "Your contract has been marked complete.", "contract_completed")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(contract_id=contract_id, status="completed"), 200


@execution_bp.get("/contracts/<int:contract_id>/tasks")
@roles_required("client", "freelancer", "admin")
def list_tasks(contract_id):
    contract, error = _authorized_contract(contract_id)
    if error:
        return error
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT task_id, contract_id, title, description, assigned_to, due_date, status, created_at "
            "FROM Task WHERE contract_id = %s ORDER BY task_id",
            (contract_id,),
        )
        tasks = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(tasks=tasks), 200


@execution_bp.post("/contracts/<int:contract_id>/tasks")
@roles_required("client")
def create_task(contract_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {"title", "description", "due_date"}:
        return _bad_request("Provide title and optional description and due_date only.")
    title = body.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 180:
        return _bad_request("title is required and limited to 180 characters.")
    description = body.get("description")
    if description is not None and not isinstance(description, str):
        return _bad_request("description must be a string or null.")
    due_date, error = _parse_date(body.get("due_date"))
    if error:
        return error

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        contract, error = _select_contract(cursor, contract_id, lock=True)
        if error:
            connection.rollback()
            return error
        if contract["client_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Contract was not found.")
        if contract["status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Tasks can only be added to active contracts.")
        cursor.execute(
            "INSERT INTO Task (contract_id, title, description, assigned_to, due_date) VALUES (%s, %s, %s, %s, %s)",
            (contract_id, title.strip(), description, contract["freelancer_id"], due_date),
        )
        task_id = cursor.lastrowid
        add_notification(cursor, contract["freelancer_id"], "A task was assigned to your contract.", "task_assigned")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(task_id=task_id, status="todo", assigned_to=contract["freelancer_id"]), 201


@execution_bp.patch("/tasks/<int:task_id>")
@roles_required("client", "freelancer")
def update_task(task_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body:
        return _bad_request("A non-empty JSON object is required.")
    role = get_jwt().get("role")
    client_fields = {"title", "description", "due_date", "status"}
    if set(body) - client_fields:
        return _bad_request("One or more task fields are not editable.")
    if role == "freelancer" and set(body) != {"status"}:
        return _bad_request("Freelancers may update task status only.")
    values = {}
    if "title" in body:
        if not isinstance(body["title"], str) or not body["title"].strip() or len(body["title"].strip()) > 180:
            return _bad_request("title is required and limited to 180 characters.")
        values["title"] = body["title"].strip()
    if "description" in body:
        if body["description"] is not None and not isinstance(body["description"], str):
            return _bad_request("description must be a string or null.")
        values["description"] = body["description"]
    if "due_date" in body:
        due_date, error = _parse_date(body["due_date"])
        if error:
            return error
        values["due_date"] = due_date
    next_status = body.get("status")
    if "status" in body and (not isinstance(next_status, str) or next_status not in {"todo", "in_progress", "submitted", "completed", "cancelled"}):
        return _bad_request("Invalid task status.")

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT t.task_id, t.contract_id, t.assigned_to, t.status, p.client_id, a.freelancer_id, c.status AS contract_status "
            "FROM Task t JOIN Contract c ON c.contract_id = t.contract_id "
            "JOIN Project p ON p.project_id = c.project_id "
            "JOIN Application a ON a.application_id = c.application_id "
            "WHERE t.task_id = %s FOR UPDATE",
            (task_id,),
        )
        task = cursor.fetchone()
        if not task:
            connection.rollback()
            return _not_found("Task was not found.")
        identity = int(get_jwt_identity())
        if role == "client" and task["client_id"] != identity:
            connection.rollback()
            return _not_found("Task was not found.")
        if role == "freelancer" and task["assigned_to"] != identity:
            connection.rollback()
            return _not_found("Task was not found.")
        if task["contract_status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Tasks on a closed contract cannot be changed.")
        if "status" in body:
            if role == "freelancer":
                allowed = {"todo": {"in_progress", "submitted"}, "in_progress": {"submitted"}}
                if next_status not in allowed.get(task["status"], set()):
                    connection.rollback()
                    return _conflict("invalid_task_transition", "Freelancers may move a task from todo to in_progress, then to submitted.")
            else:
                if next_status == "completed" and task["status"] != "submitted":
                    connection.rollback()
                    return _conflict("task_not_submitted", "A task must be submitted before the client can complete it.")
                if next_status == "cancelled" and task["status"] in {"completed", "cancelled"}:
                    connection.rollback()
                    return _conflict("invalid_task_transition", "Completed or cancelled tasks cannot be cancelled again.")
                if next_status not in {"completed", "cancelled"}:
                    connection.rollback()
                    return _bad_request("Clients may set task status to completed or cancelled.")
            values["status"] = next_status
        if not values:
            connection.rollback()
            return _bad_request("Provide at least one task field to update.")
        assignments = ", ".join(f"{column} = %s" for column in values)
        cursor.execute(f"UPDATE Task SET {assignments} WHERE task_id = %s", (*values.values(), task_id))
        if next_status == "submitted":
            add_notification(cursor, task["client_id"], "A task was submitted for review.", "task_submitted")
        elif next_status in {"completed", "cancelled"}:
            add_notification(cursor, task["assigned_to"], f"A task was marked {next_status}.", f"task_{next_status}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(task_id=task_id, **values), 200


@execution_bp.get("/contracts/<int:contract_id>/milestones")
@roles_required("client", "freelancer", "admin")
def list_milestones(contract_id):
    _contract, error = _authorized_contract(contract_id)
    if error:
        return error
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT milestone_id, contract_id, title, description, amount, due_date, status, submitted_at, reviewed_at "
            "FROM Milestone WHERE contract_id = %s ORDER BY milestone_id",
            (contract_id,),
        )
        milestones = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(milestones=milestones), 200


@execution_bp.post("/contracts/<int:contract_id>/milestones")
@roles_required("client")
def create_milestone(contract_id):
    body = request.get_json(silent=True)
    allowed = {"title", "description", "amount", "due_date"}
    if not isinstance(body, dict) or set(body) - allowed or not {"title", "amount"} <= set(body):
        return _bad_request("Provide title and amount, with optional description and due_date.")
    title = body["title"]
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 180:
        return _bad_request("title is required and limited to 180 characters.")
    description = body.get("description")
    if description is not None and not isinstance(description, str):
        return _bad_request("description must be a string or null.")
    try:
        amount = Decimal(str(body["amount"]))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99"):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        return _bad_request("amount must be positive and no greater than 9999999999.99.")
    due_date, error = _parse_date(body.get("due_date"))
    if error:
        return error

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        contract, error = _select_contract(cursor, contract_id, lock=True)
        if error:
            connection.rollback()
            return error
        if contract["client_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Contract was not found.")
        if contract["status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Milestones can only be added to active contracts.")
        cursor.execute("SELECT amount FROM Milestone WHERE contract_id = %s FOR UPDATE", (contract_id,))
        allocated = sum((Decimal(str(row["amount"])) for row in cursor.fetchall()), Decimal("0"))
        if allocated + amount > Decimal(str(contract["agreed_amount"])):
            connection.rollback()
            return _conflict("milestone_budget_exceeded", "Milestone amounts cannot exceed the contract amount.")
        cursor.execute(
            "INSERT INTO Milestone (contract_id, title, description, amount, due_date) VALUES (%s, %s, %s, %s, %s)",
            (contract_id, title.strip(), description, amount, due_date),
        )
        milestone_id = cursor.lastrowid
        add_notification(cursor, contract["freelancer_id"], "A milestone was added to your contract.", "milestone_added")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(milestone_id=milestone_id, status="pending"), 201


@execution_bp.patch("/milestones/<int:milestone_id>/submit")
@roles_required("freelancer")
def submit_milestone(milestone_id):
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT m.status, c.status AS contract_status, a.freelancer_id, p.client_id FROM Milestone m "
            "JOIN Contract c ON c.contract_id = m.contract_id "
            "JOIN Application a ON a.application_id = c.application_id "
            "JOIN Project p ON p.project_id = c.project_id "
            "WHERE m.milestone_id = %s FOR UPDATE",
            (milestone_id,),
        )
        milestone = cursor.fetchone()
        if not milestone or milestone["freelancer_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Milestone was not found.")
        if milestone["contract_status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Milestones on a closed contract cannot be submitted.")
        if milestone["status"] not in {"pending", "rejected"}:
            connection.rollback()
            return _conflict("invalid_milestone_transition", "Only pending or rejected milestones can be submitted.")
        cursor.execute(
            "UPDATE Milestone SET status = 'submitted', submitted_at = CURRENT_TIMESTAMP, reviewed_at = NULL WHERE milestone_id = %s",
            (milestone_id,),
        )
        add_notification(cursor, milestone["client_id"], "A milestone was submitted for review.", "milestone_submitted")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(milestone_id=milestone_id, status="submitted"), 200


@execution_bp.patch("/milestones/<int:milestone_id>/review")
@roles_required("client")
def review_milestone(milestone_id):
    body = request.get_json(silent=True)
    status = body.get("status") if isinstance(body, dict) else None
    if not isinstance(body, dict) or set(body) != {"status"} or not isinstance(status, str) or status not in {"approved", "rejected"}:
        return _bad_request("status must be approved or rejected.")
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT m.status, c.status AS contract_status, p.client_id, a.freelancer_id FROM Milestone m "
            "JOIN Contract c ON c.contract_id = m.contract_id JOIN Project p ON p.project_id = c.project_id "
            "JOIN Application a ON a.application_id = c.application_id "
            "WHERE m.milestone_id = %s FOR UPDATE",
            (milestone_id,),
        )
        milestone = cursor.fetchone()
        if not milestone or milestone["client_id"] != int(get_jwt_identity()):
            connection.rollback()
            return _not_found("Milestone was not found.")
        if milestone["contract_status"] != "active":
            connection.rollback()
            return _conflict("contract_closed", "Milestones on a closed contract cannot be reviewed.")
        if milestone["status"] != "submitted":
            connection.rollback()
            return _conflict("milestone_not_submitted", "Only submitted milestones can be reviewed.")
        cursor.execute(
            "UPDATE Milestone SET status = %s, reviewed_at = CURRENT_TIMESTAMP WHERE milestone_id = %s",
            (status, milestone_id),
        )
        add_notification(cursor, milestone["freelancer_id"], f"Your milestone was {status}.", f"milestone_{status}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(milestone_id=milestone_id, status=status), 200


def _authorized_contract(contract_id):
    role = get_jwt().get("role")
    cursor = get_db().cursor(dictionary=True)
    try:
        contract, error = _select_contract(cursor, contract_id)
    finally:
        cursor.close()
    if error:
        return None, error
    identity = int(get_jwt_identity())
    if role != "admin" and identity not in {contract["client_id"], contract["freelancer_id"]}:
        return None, _not_found("Contract was not found.")
    return contract, None


def _select_contract(cursor, contract_id, lock=False):
    query = f"{CONTRACT_SELECT} WHERE c.contract_id = %s"
    if lock:
        query += " FOR UPDATE"
    cursor.execute(query, (contract_id,))
    contract = cursor.fetchone()
    if not contract:
        return None, _not_found("Contract was not found.")
    return contract, None


def _parse_date(value):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _bad_request("Date fields must use YYYY-MM-DD or null.")
    try:
        return date.fromisoformat(value).isoformat(), None
    except ValueError:
        return None, _bad_request("Date fields must use YYYY-MM-DD or null.")


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400


def _not_found(message):
    return jsonify(error={"code": "not_found", "message": message}), 404


def _conflict(code, message):
    return jsonify(error={"code": code, "message": message}), 409
