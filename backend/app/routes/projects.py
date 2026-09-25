"""Project discovery, client project management, and application bidding."""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from mysql.connector import IntegrityError

from app.db import get_db
from app.utils.notifications import add_notification
from app.utils.auth import roles_required

projects_bp = Blueprint("projects", __name__)
PROJECT_COLUMNS = {
    "title", "description", "category_id", "budget_min", "budget_max",
    "deadline", "project_type", "status",
}
PROJECT_SORTS = {
    "newest": "p.created_at DESC, p.project_id DESC",
    "oldest": "p.created_at ASC, p.project_id ASC",
    "deadline": "p.deadline ASC, p.project_id DESC",
    "budget_low": "p.budget_min ASC, p.project_id DESC",
    "budget_high": "p.budget_max DESC, p.project_id DESC",
}
PROJECT_STATUSES = {"draft", "open", "in_progress", "completed", "cancelled"}
EDITABLE_STATUSES = {"draft", "open", "cancelled"}
PROJECT_SELECT = (
    "SELECT p.project_id, p.client_id, p.category_id, c.name AS category_name, "
    "u.full_name AS client_name, p.title, p.description, p.budget_min, p.budget_max, "
    "p.deadline, p.project_type, p.status, p.created_at, p.updated_at "
    "FROM Project p JOIN Category c ON c.category_id = p.category_id "
    "JOIN `User` u ON u.user_id = p.client_id"
)


class InvalidProjectReference(ValueError):
    """A category or skill identifier does not exist in the catalog."""


@projects_bp.get("/projects")
def search_projects():
    filters, error = _search_filters()
    if error:
        return error
    requested_status = request.args.get("status")
    if requested_status and requested_status != "open":
        return _bad_request("Public search supports open projects only; use /api/projects/mine for your own projects.")
    clauses = ["p.status = 'open'"]
    params = []
    _append_search_conditions(clauses, params, filters)
    where = " AND ".join(clauses)
    query = f"{PROJECT_SELECT} WHERE {where} ORDER BY {PROJECT_SORTS[filters['sort']]} LIMIT %s OFFSET %s"
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(query, (*params, filters["limit"], filters["offset"]))
        projects = cursor.fetchall()
        _load_project_skills(cursor, projects)
    except ValueError as error:
        if str(error) == "project_type":
            return _bad_request("project_type must be fixed or hourly.")
        return _bad_request("deadline_before and deadline_after must be ISO dates (YYYY-MM-DD).")
    finally:
        cursor.close()
    return jsonify(projects=projects, limit=filters["limit"], offset=filters["offset"]), 200


@projects_bp.get("/projects/mine")
@roles_required("client")
def list_my_projects():
    client_id = int(get_jwt_identity())
    limit, offset = _pagination()
    if limit is None:
        return _bad_request("limit must be 1–100 and offset must be zero or greater.")
    status = request.args.get("status")
    if status and status not in PROJECT_STATUSES:
        return _bad_request("Invalid project status filter.")
    clauses, params = ["p.client_id = %s"], [client_id]
    if status:
        clauses.append("p.status = %s")
        params.append(status)
    query = f"{PROJECT_SELECT} WHERE {' AND '.join(clauses)} ORDER BY p.created_at DESC, p.project_id DESC LIMIT %s OFFSET %s"
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(query, (*params, limit, offset))
        projects = cursor.fetchall()
        _load_project_skills(cursor, projects)
    finally:
        cursor.close()
    return jsonify(projects=projects, limit=limit, offset=offset), 200


@projects_bp.post("/projects")
@roles_required("client")
def create_project():
    body = request.get_json(silent=True)
    values, skill_ids, error = _validate_project(body)
    if error:
        return error
    if values.get("status", "open") not in {"draft", "open"}:
        return _bad_request("New projects may start as draft or open.")
    values.setdefault("status", "open")
    connection = get_db()
    cursor = connection.cursor()
    try:
        _ensure_category_and_skills(cursor, values["category_id"], skill_ids)
        columns = ["client_id", *values]
        placeholders = ", ".join(["%s"] * len(columns))
        cursor.execute(
            f"INSERT INTO Project ({', '.join(columns)}) VALUES ({placeholders})",
            (int(get_jwt_identity()), *values.values()),
        )
        project_id = cursor.lastrowid
        _replace_project_skills(cursor, project_id, skill_ids)
        connection.commit()
    except InvalidProjectReference as error:
        connection.rollback()
        return _bad_request(str(error))
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(project_id=project_id, message="Project created."), 201


@projects_bp.get("/projects/<int:project_id>")
def get_project(project_id):
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(f"{PROJECT_SELECT} WHERE p.project_id = %s", (project_id,))
        project = cursor.fetchone()
        if not project:
            return _not_found("Project was not found.")
        if project["status"] != "open":
            if identity is None:
                return _not_found("Project was not found.")
            cursor.execute("SELECT role, account_status FROM `User` WHERE user_id = %s", (int(identity),))
            viewer = cursor.fetchone()
            if not viewer or viewer["account_status"] != "active":
                return jsonify(error={"code": "account_inactive", "message": "This account is not active."}), 401
            if viewer["role"] != "admin" and not (viewer["role"] == "client" and int(identity) == project["client_id"]):
                return _not_found("Project was not found.")
        _load_project_skills(cursor, [project])
    finally:
        cursor.close()
    return jsonify(project=project), 200


@projects_bp.patch("/projects/<int:project_id>")
@roles_required("client")
def update_project(project_id):
    body = request.get_json(silent=True)
    values, skill_ids, error = _validate_project(body, partial=True)
    if error:
        return error
    if not values and skill_ids is None:
        return _bad_request("Provide at least one editable project field or skill_ids.")
    if "status" in values and values["status"] not in EDITABLE_STATUSES:
        return _bad_request("Clients may set status to draft, open, or cancelled.")

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT project_id, category_id, status, budget_min, budget_max FROM Project "
            "WHERE project_id = %s AND client_id = %s FOR UPDATE",
            (project_id, int(get_jwt_identity())),
        )
        existing = cursor.fetchone()
        if not existing:
            connection.rollback()
            return _not_found("Project was not found.")
        if existing["status"] not in {"draft", "open"}:
            connection.rollback()
            return jsonify(error={"code": "project_locked", "message": "Only draft or open projects can be edited."}), 409
        category_id = values.get("category_id", existing["category_id"])
        minimum = values.get("budget_min", existing["budget_min"])
        maximum = values.get("budget_max", existing["budget_max"])
        if maximum < minimum:
            connection.rollback()
            return _bad_request("budget_max must be greater than or equal to budget_min.")
        if "status" in values and values["status"] not in EDITABLE_STATUSES:
            connection.rollback()
            return _bad_request("Clients may set status to draft, open, or cancelled.")
        if values or skill_ids is not None:
            _ensure_category_and_skills(cursor, category_id, skill_ids or [])
        if values:
            assignments = ", ".join(f"{column} = %s" for column in values)
            cursor.execute(
                f"UPDATE Project SET {assignments} WHERE project_id = %s AND client_id = %s",
                (*values.values(), project_id, int(get_jwt_identity())),
            )
        if skill_ids is not None:
            _replace_project_skills(cursor, project_id, skill_ids)
        connection.commit()
    except InvalidProjectReference as error:
        connection.rollback()
        return _bad_request(str(error))
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(message="Project updated."), 200


@projects_bp.delete("/projects/<int:project_id>")
@roles_required("client")
def cancel_project(project_id):
    """Soft-delete an editable project by setting its status to cancelled."""
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE Project SET status = 'cancelled' WHERE project_id = %s AND client_id = %s AND status IN ('draft','open')",
            (project_id, int(get_jwt_identity())),
        )
        changed = cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    if not changed:
        return _not_found("Editable project was not found.")
    return jsonify(message="Project cancelled."), 200


@projects_bp.get("/projects/<int:project_id>/applications")
@roles_required("client")
def list_project_applications(project_id):
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT a.application_id, a.project_id, a.freelancer_id, u.full_name AS freelancer_name, "
            "f.headline, f.hourly_rate, a.proposal, a.bid_amount, a.estimated_days, a.status, a.applied_at "
            "FROM Application a JOIN Project p ON p.project_id = a.project_id "
            "JOIN `User` u ON u.user_id = a.freelancer_id "
            "JOIN Freelancer f ON f.user_id = a.freelancer_id "
            "WHERE a.project_id = %s AND p.client_id = %s ORDER BY a.applied_at DESC, a.application_id DESC",
            (project_id, int(get_jwt_identity())),
        )
        applications = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(applications=applications), 200


@projects_bp.get("/applications/mine")
@roles_required("freelancer")
def list_my_applications():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT a.application_id, a.project_id, p.title AS project_title, c.name AS category_name, "
            "a.proposal, a.bid_amount, a.estimated_days, a.status, a.applied_at "
            "FROM Application a JOIN Project p ON p.project_id = a.project_id "
            "JOIN Category c ON c.category_id = p.category_id "
            "WHERE a.freelancer_id = %s ORDER BY a.applied_at DESC, a.application_id DESC",
            (int(get_jwt_identity()),),
        )
        applications = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(applications=applications), 200


@projects_bp.post("/projects/<int:project_id>/applications")
@roles_required("freelancer")
def apply_to_project(project_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"proposal", "bid_amount", "estimated_days"}:
        return _bad_request("Provide proposal, bid_amount, and estimated_days only.")
    proposal = body["proposal"]
    if not isinstance(proposal, str) or not proposal.strip():
        return _bad_request("proposal is required.")
    try:
        bid = Decimal(str(body["bid_amount"]))
        if not bid.is_finite() or bid <= 0 or bid > Decimal("9999999999.99"):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        return _bad_request("bid_amount must be a positive amount up to 9999999999.99.")
    days = body["estimated_days"]
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 65535:
        return _bad_request("estimated_days must be a whole number from 1 to 65535.")

    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT status FROM Project WHERE project_id = %s", (project_id,))
        project = cursor.fetchone()
        if not project or project[0] != "open":
            connection.rollback()
            return _not_found("Open project was not found.")
        cursor.execute(
            "INSERT INTO Application (project_id, freelancer_id, proposal, bid_amount, estimated_days) "
            "VALUES (%s, %s, %s, %s, %s)",
            (project_id, int(get_jwt_identity()), proposal.strip(), bid, days),
        )
        application_id = cursor.lastrowid
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        if error.errno == 1062:
            return jsonify(error={"code": "application_exists", "message": "You have already applied to this project."}), 409
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(application_id=application_id, status="pending", message="Application submitted."), 201


@projects_bp.patch("/applications/<int:application_id>/status")
@roles_required("client")
def update_application_status(application_id):
    body = request.get_json(silent=True)
    next_status = body.get("status") if isinstance(body, dict) else None
    if (
        not isinstance(body, dict)
        or set(body) - {"status", "agreed_amount"}
        or "status" not in body
        or not isinstance(next_status, str)
        or next_status not in {"shortlisted", "accepted", "rejected"}
    ):
        return _bad_request("status must be shortlisted, accepted, or rejected.")
    if "agreed_amount" in body and next_status != "accepted":
        return _bad_request("agreed_amount is only valid when accepting an application.")
    agreed_amount = None
    if "agreed_amount" in body:
        try:
            agreed_amount = Decimal(str(body["agreed_amount"]))
            if not agreed_amount.is_finite() or agreed_amount <= 0 or agreed_amount > Decimal("9999999999.99"):
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            return _bad_request("agreed_amount must be a positive amount up to 9999999999.99.")
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT a.application_id, a.project_id, a.freelancer_id, a.bid_amount, "
            "a.status AS application_status, p.status AS project_status "
            "FROM Application a JOIN Project p ON p.project_id = a.project_id "
            "WHERE a.application_id = %s AND p.client_id = %s FOR UPDATE",
            (application_id, int(get_jwt_identity())),
        )
        application = cursor.fetchone()
        if not application:
            connection.rollback()
            return _not_found("Application was not found.")
        current_status = application["application_status"]
        if current_status in {"accepted", "rejected", "withdrawn"}:
            connection.rollback()
            return jsonify(error={"code": "application_locked", "message": "This application can no longer be changed."}), 409
        if next_status == "accepted":
            if application["project_status"] != "open":
                connection.rollback()
                return jsonify(error={"code": "project_unavailable", "message": "This project is no longer open for hiring."}), 409
            cursor.execute(
                "SELECT COUNT(*) AS accepted_count FROM Application WHERE project_id = %s AND status = 'accepted'",
                (application["project_id"],),
            )
            if cursor.fetchone()["accepted_count"]:
                connection.rollback()
                return jsonify(error={"code": "project_already_filled", "message": "A project can have only one accepted application."}), 409
        if next_status == "shortlisted" and current_status != "pending":
            connection.rollback()
            return jsonify(error={"code": "invalid_transition", "message": "Only pending applications can be shortlisted."}), 409
        cursor.execute("UPDATE Application SET status = %s WHERE application_id = %s", (next_status, application_id))
        if next_status == "accepted":
            cursor.execute("UPDATE Project SET status = 'in_progress' WHERE project_id = %s", (application["project_id"],))
            contract_amount = agreed_amount if agreed_amount is not None else application["bid_amount"]
            cursor.execute(
                "INSERT INTO Contract (project_id, application_id, start_date, agreed_amount) "
                "VALUES (%s, %s, CURRENT_DATE(), %s)",
                (application["project_id"], application_id, contract_amount),
            )
            contract_id = cursor.lastrowid
        add_notification(
            cursor,
            application["freelancer_id"],
            f"Your application was {next_status}.",
            "application_status",
        )
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        if error.errno == 1062:
            return jsonify(error={"code": "contract_exists", "message": "This project already has a contract."}), 409
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    response = {"application_id": application_id, "status": next_status}
    if next_status == "accepted":
        response["contract_id"] = contract_id
    return jsonify(response), 200


def _search_filters():
    limit, offset = _pagination()
    if limit is None:
        return None, _bad_request("limit must be 1–100 and offset must be zero or greater.")
    sort = request.args.get("sort", "newest")
    if sort not in PROJECT_SORTS:
        return None, _bad_request("sort must be newest, oldest, deadline, budget_low, or budget_high.")
    category_id = _query_positive_int("category_id")
    if category_id is False:
        return None, _bad_request("category_id must be a positive integer.")
    skill_ids = []
    for value in request.args.getlist("skill_id"):
        parsed = _parse_int(value)
        if parsed is None or parsed < 1:
            return None, _bad_request("Each skill_id must be a positive integer.")
        if parsed not in skill_ids:
            skill_ids.append(parsed)
    budget_min, error = _query_decimal("budget_min")
    if error:
        return None, error
    budget_max, error = _query_decimal("budget_max")
    if error:
        return None, error
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        return None, _bad_request("budget_min cannot exceed budget_max.")
    project_type = request.args.get("project_type")
    if project_type and project_type not in {"fixed", "hourly"}:
        return None, _bad_request("project_type must be fixed or hourly.")
    for key in ("deadline_before", "deadline_after"):
        value = request.args.get(key)
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                return None, _bad_request(f"{key} must be an ISO date (YYYY-MM-DD).")
    return {
        "limit": limit, "offset": offset, "sort": sort,
        "q": request.args.get("q", "").strip(), "category_id": category_id,
        "skill_ids": skill_ids, "budget_min": budget_min, "budget_max": budget_max,
        "project_type": project_type,
        "deadline_before": request.args.get("deadline_before"),
        "deadline_after": request.args.get("deadline_after"),
    }, None


def _append_search_conditions(clauses, params, filters):
    if filters["q"]:
        clauses.append("(p.title LIKE %s OR p.description LIKE %s)")
        params.extend((f"%{filters['q']}%", f"%{filters['q']}%"))
    if filters["category_id"]:
        clauses.append("p.category_id = %s")
        params.append(filters["category_id"])
    if filters["skill_ids"]:
        placeholders = ", ".join(["%s"] * len(filters["skill_ids"]))
        clauses.append(
            "EXISTS (SELECT 1 FROM Project_Skill ps WHERE ps.project_id = p.project_id "
            f"AND ps.skill_id IN ({placeholders}) GROUP BY ps.project_id HAVING COUNT(DISTINCT ps.skill_id) = %s)"
        )
        params.extend(filters["skill_ids"])
        params.append(len(filters["skill_ids"]))
    if filters["budget_min"] is not None:
        clauses.append("p.budget_max >= %s")
        params.append(filters["budget_min"])
    if filters["budget_max"] is not None:
        clauses.append("p.budget_min <= %s")
        params.append(filters["budget_max"])
    if filters["project_type"]:
        clauses.append("p.project_type = %s")
        params.append(filters["project_type"])
    for key, operator in (("deadline_before", "<="), ("deadline_after", ">=")):
        value = filters[key]
        if value:
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError(key)
            clauses.append(f"p.deadline {operator} %s")
            params.append(parsed.isoformat())


def _load_project_skills(cursor, projects):
    for project in projects:
        project["required_skills"] = []
    project_ids = [project["project_id"] for project in projects]
    if not project_ids:
        return
    placeholders = ", ".join(["%s"] * len(project_ids))
    cursor.execute(
        "SELECT ps.project_id, s.skill_id, s.name FROM Project_Skill ps "
        "JOIN Skill s ON s.skill_id = ps.skill_id "
        f"WHERE ps.project_id IN ({placeholders}) ORDER BY s.name",
        tuple(project_ids),
    )
    by_id = {project_id: project for project_id, project in zip(project_ids, projects)}
    for row in cursor.fetchall():
        by_id[row["project_id"]]["required_skills"].append({"skill_id": row["skill_id"], "name": row["name"]})


def _validate_project(body, partial=False):
    if not isinstance(body, dict) or not body:
        return {}, None, _bad_request("A non-empty JSON object is required.")
    allowed = PROJECT_COLUMNS | {"skill_ids"}
    if set(body) - allowed:
        return {}, None, _bad_request("One or more project fields are not supported.")
    values = {}
    required = {"title", "description", "category_id", "budget_min", "budget_max", "project_type"}
    missing = required - set(body)
    if missing and not partial:
        return {}, None, _bad_request(f"Missing required fields: {', '.join(sorted(missing))}.")
    for column in ("title", "description"):
        if column in body:
            value = body[column]
            max_length = 180 if column == "title" else None
            if not isinstance(value, str) or not value.strip() or (max_length and len(value.strip()) > max_length):
                return {}, None, _bad_request(f"{column} is required" + (" and limited to 180 characters." if max_length else "."))
            values[column] = value.strip()
    if "category_id" in body:
        value = body["category_id"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return {}, None, _bad_request("category_id must be a positive integer.")
        values["category_id"] = value
    for column in ("budget_min", "budget_max"):
        if column in body:
            try:
                amount = Decimal(str(body[column]))
                if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999.99"):
                    raise InvalidOperation
            except (InvalidOperation, TypeError, ValueError):
                return {}, None, _bad_request(f"{column} must be a non-negative amount up to 9999999999.99.")
            values[column] = amount
    minimum, maximum = values.get("budget_min"), values.get("budget_max")
    if minimum is not None and maximum is not None and maximum < minimum:
        return {}, None, _bad_request("budget_max must be greater than or equal to budget_min.")
    if "project_type" in body:
        if not isinstance(body["project_type"], str) or body["project_type"] not in {"fixed", "hourly"}:
            return {}, None, _bad_request("project_type must be fixed or hourly.")
        values["project_type"] = body["project_type"]
    if "deadline" in body:
        value = body["deadline"]
        if value is not None:
            try:
                value = date.fromisoformat(value).isoformat() if isinstance(value, str) else None
            except ValueError:
                value = None
            if value is None:
                return {}, None, _bad_request("deadline must be an ISO date (YYYY-MM-DD) or null.")
        values["deadline"] = value
    if "status" in body:
        if not isinstance(body["status"], str) or body["status"] not in PROJECT_STATUSES:
            return {}, None, _bad_request("Invalid project status.")
        values["status"] = body["status"]
    skill_ids = None
    if "skill_ids" in body:
        skill_ids = body["skill_ids"]
        if not isinstance(skill_ids, list):
            return {}, None, _bad_request("skill_ids must be a list of positive skill IDs.")
        if any(isinstance(skill_id, bool) or not isinstance(skill_id, int) or skill_id < 1 for skill_id in skill_ids):
            return {}, None, _bad_request("Each skill_id must be a positive integer.")
        if len(set(skill_ids)) != len(skill_ids):
            return {}, None, _bad_request("skill_ids must not contain duplicates.")
    return values, skill_ids, None


def _ensure_category_and_skills(cursor, category_id, skill_ids):
    cursor.execute("SELECT category_id FROM Category WHERE category_id = %s", (category_id,))
    if not cursor.fetchone():
        raise InvalidProjectReference("category_id does not refer to an existing category.")
    if skill_ids:
        placeholders = ", ".join(["%s"] * len(skill_ids))
        cursor.execute(f"SELECT skill_id FROM Skill WHERE skill_id IN ({placeholders})", tuple(skill_ids))
        found = {row[0] if not isinstance(row, dict) else row["skill_id"] for row in cursor.fetchall()}
        if found != set(skill_ids):
            raise InvalidProjectReference("One or more skill_ids do not exist.")


def _replace_project_skills(cursor, project_id, skill_ids):
    cursor.execute("DELETE FROM Project_Skill WHERE project_id = %s", (project_id,))
    if skill_ids:
        cursor.executemany(
            "INSERT INTO Project_Skill (project_id, skill_id) VALUES (%s, %s)",
            [(project_id, skill_id) for skill_id in skill_ids],
        )


def _pagination():
    limit, offset = _parse_int(request.args.get("limit", "50")), _parse_int(request.args.get("offset", "0"))
    if limit is None or offset is None or not 1 <= limit <= 100 or offset < 0:
        return None, None
    return limit, offset


def _query_positive_int(key):
    value = request.args.get(key)
    if value is None:
        return None
    parsed = _parse_int(value)
    return parsed if parsed is not None and parsed > 0 else False


def _query_decimal(key):
    value = request.args.get(key)
    if value is None:
        return None, None
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
        return amount, None
    except (InvalidOperation, TypeError, ValueError):
        return None, _bad_request(f"{key} must be a non-negative number.")


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400


def _not_found(message):
    return jsonify(error={"code": "not_found", "message": message}), 404
