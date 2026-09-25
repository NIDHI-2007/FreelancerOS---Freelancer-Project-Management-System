"""Skill catalog and freelancer-to-skill assignments."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from mysql.connector import IntegrityError

from app.db import get_db
from app.utils.auth import roles_required

skills_bp = Blueprint("skills", __name__)


@skills_bp.get("")
def list_skills():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute("SELECT skill_id, name FROM Skill ORDER BY name")
        skills = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(skills=skills), 200


@skills_bp.post("")
@roles_required("admin")
def create_skill():
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return _bad_request("name is required and limited to 100 characters.")
    cursor = get_db().cursor()
    try:
        cursor.execute("INSERT INTO Skill (name) VALUES (%s)", (name.strip(),))
        skill_id = cursor.lastrowid
        cursor.connection.commit()
    except IntegrityError as error:
        cursor.connection.rollback()
        if error.errno == 1062:
            return jsonify(error={"code": "duplicate_skill", "message": "That skill already exists."}), 409
        raise
    finally:
        cursor.close()
    return jsonify(skill={"skill_id": skill_id, "name": name.strip()}), 201


@skills_bp.patch("/<int:skill_id>")
@roles_required("admin")
def update_skill(skill_id):
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100 or set(body) != {"name"}:
        return _bad_request("Provide name only; it must contain 1–100 characters.")
    cursor = get_db().cursor()
    try:
        cursor.execute("UPDATE Skill SET name = %s WHERE skill_id = %s", (name.strip(), skill_id))
        changed = cursor.rowcount
        cursor.connection.commit()
    except IntegrityError as error:
        cursor.connection.rollback()
        if error.errno == 1062:
            return jsonify(error={"code": "duplicate_skill", "message": "That skill already exists."}), 409
        raise
    finally:
        cursor.close()
    if not changed:
        return jsonify(error={"code": "not_found", "message": "Skill was not found or its name is unchanged."}), 404
    return jsonify(skill={"skill_id": skill_id, "name": name.strip()}), 200


@skills_bp.delete("/<int:skill_id>")
@roles_required("admin")
def delete_skill(skill_id):
    cursor = get_db().cursor()
    try:
        cursor.execute("DELETE FROM Skill WHERE skill_id = %s", (skill_id,))
        deleted = cursor.rowcount
        cursor.connection.commit()
    except IntegrityError as error:
        cursor.connection.rollback()
        if error.errno == 1451:
            return jsonify(error={"code": "skill_in_use", "message": "Remove this skill from projects before deleting it."}), 409
        raise
    finally:
        cursor.close()
    if not deleted:
        return jsonify(error={"code": "not_found", "message": "Skill was not found."}), 404
    return jsonify(message="Skill deleted."), 200


@skills_bp.get("/me")
@roles_required("freelancer")
def list_my_skills():
    cursor = get_db().cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT s.skill_id, s.name, fs.proficiency_level "
            "FROM Freelancer_Skill fs JOIN Skill s ON s.skill_id = fs.skill_id "
            "WHERE fs.freelancer_id = %s ORDER BY s.name",
            (int(get_jwt_identity()),),
        )
        skills = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(skills=skills), 200


@skills_bp.put("/me")
@roles_required("freelancer")
def replace_my_skills():
    body = request.get_json(silent=True)
    items = body.get("skills") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return _bad_request("skills must be a list of {skill_id, proficiency_level} objects.")
    assignments = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"skill_id", "proficiency_level"}:
            return _bad_request("Each skill must contain skill_id and proficiency_level only.")
        skill_id, level = item["skill_id"], item["proficiency_level"]
        if isinstance(skill_id, bool) or not isinstance(skill_id, int) or skill_id < 1:
            return _bad_request("skill_id must be a positive integer.")
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 5:
            return _bad_request("proficiency_level must be an integer from 1 to 5.")
        if skill_id in seen:
            return _bad_request("Each skill_id may appear only once.")
        seen.add(skill_id)
        assignments.append((skill_id, level))

    connection = get_db()
    cursor = connection.cursor()
    try:
        if assignments:
            placeholders = ", ".join(["%s"] * len(assignments))
            cursor.execute(f"SELECT skill_id FROM Skill WHERE skill_id IN ({placeholders})", tuple(i[0] for i in assignments))
            found = {row[0] for row in cursor.fetchall()}
            missing = seen - found
            if missing:
                return jsonify(error={"code": "unknown_skill", "message": "One or more skill IDs do not exist.", "skill_ids": sorted(missing)}), 400
        freelancer_id = int(get_jwt_identity())
        cursor.execute("DELETE FROM Freelancer_Skill WHERE freelancer_id = %s", (freelancer_id,))
        if assignments:
            cursor.executemany(
                "INSERT INTO Freelancer_Skill (freelancer_id, skill_id, proficiency_level) VALUES (%s, %s, %s)",
                [(freelancer_id, skill_id, level) for skill_id, level in assignments],
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(message="Skills updated.", count=len(assignments)), 200


def _bad_request(message):
    return jsonify(error={"code": "invalid_request", "message": message}), 400
