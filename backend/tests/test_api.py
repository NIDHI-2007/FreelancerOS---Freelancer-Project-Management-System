"""API tests using SQLite as a local SQL test double; production uses MySQL."""

import sqlite3
import re
import sys
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import mysql.connector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from flask_jwt_extended import create_access_token  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402
from app.utils.notifications import add_notification  # noqa: E402


class TestCursor:
    def __init__(self, connection, dictionary=False):
        self.connection = connection
        self.dictionary = dictionary
        self.cursor = connection.raw.cursor()

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def execute(self, sql, params=()):
        sql = sql.replace(" FOR UPDATE", "").replace("CURRENT_DATE()", "CURRENT_DATE").replace("UTC_TIMESTAMP()", "CURRENT_TIMESTAMP").replace("%s", "?")
        try:
            self.cursor.execute(sql, self._params(params))
        except sqlite3.IntegrityError as error:
            raise mysql.connector.IntegrityError(errno=1062, msg=str(error)) from error

    def executemany(self, sql, params):
        try:
            self.cursor.executemany(sql.replace("%s", "?"), [self._params(row) for row in params])
        except sqlite3.IntegrityError as error:
            raise mysql.connector.IntegrityError(errno=1062, msg=str(error)) from error

    @staticmethod
    def _params(params):
        return tuple(str(value) if isinstance(value, Decimal) else value.isoformat(sep=" ") if isinstance(value, datetime) else value for value in params)

    def _row(self, row):
        if row is None or not self.dictionary:
            return row
        return dict(row)

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]

    def close(self):
        self.cursor.close()


class TestConnection:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        self.raw.executescript(
            """
            CREATE TABLE `User` (
              user_id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL,
              account_status TEXT NOT NULL DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Revoked_Token (
              token_jti TEXT PRIMARY KEY, expires_at TEXT NOT NULL, revoked_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Client (
              user_id INTEGER PRIMARY KEY, company_name TEXT, bio TEXT, location TEXT, website TEXT
            );
            CREATE TABLE Freelancer (
              user_id INTEGER PRIMARY KEY, headline TEXT, bio TEXT, hourly_rate NUMERIC NOT NULL DEFAULT 0,
              experience_years INTEGER NOT NULL DEFAULT 0, location TEXT, availability_status TEXT NOT NULL DEFAULT 'available'
            );
            CREATE TABLE Skill (skill_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
            CREATE TABLE Freelancer_Skill (
              freelancer_id INTEGER NOT NULL, skill_id INTEGER NOT NULL, proficiency_level INTEGER NOT NULL,
              PRIMARY KEY (freelancer_id, skill_id)
            );
            CREATE TABLE Portfolio (
              portfolio_id INTEGER PRIMARY KEY AUTOINCREMENT, freelancer_id INTEGER NOT NULL,
              title TEXT NOT NULL, description TEXT, project_url TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Category (category_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT);
            CREATE TABLE Project (
              project_id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, category_id INTEGER NOT NULL,
              title TEXT NOT NULL, description TEXT NOT NULL, budget_min NUMERIC NOT NULL, budget_max NUMERIC NOT NULL,
              deadline TEXT, project_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Project_Skill (project_id INTEGER NOT NULL, skill_id INTEGER NOT NULL, PRIMARY KEY(project_id,skill_id));
            CREATE TABLE Application (
              application_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, freelancer_id INTEGER NOT NULL,
              proposal TEXT NOT NULL, bid_amount NUMERIC NOT NULL, estimated_days INTEGER NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending', applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(project_id, freelancer_id)
            );
            CREATE TABLE Contract (
              contract_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL UNIQUE,
              application_id INTEGER NOT NULL UNIQUE, start_date TEXT NOT NULL, end_date TEXT,
              agreed_amount NUMERIC NOT NULL, status TEXT NOT NULL DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Task (
              task_id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, title TEXT NOT NULL,
              description TEXT, assigned_to INTEGER NOT NULL, due_date TEXT, status TEXT NOT NULL DEFAULT 'todo',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Milestone (
              milestone_id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, title TEXT NOT NULL,
              description TEXT, amount NUMERIC NOT NULL, due_date TEXT, status TEXT NOT NULL DEFAULT 'pending',
              submitted_at TEXT, reviewed_at TEXT, UNIQUE(contract_id,title)
            );
            CREATE TABLE Payment (
              payment_id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, milestone_id INTEGER,
              payer_id INTEGER NOT NULL, payee_id INTEGER NOT NULL, amount NUMERIC NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending', payment_method TEXT, transaction_reference TEXT UNIQUE,
              paid_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Review (
              review_id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, reviewer_id INTEGER NOT NULL,
              reviewee_id INTEGER NOT NULL, rating INTEGER NOT NULL, comment TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(contract_id,reviewer_id)
            );
            CREATE TABLE Message (
              message_id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, sender_id INTEGER NOT NULL,
              receiver_id INTEGER NOT NULL, body TEXT NOT NULL, sent_at TEXT DEFAULT CURRENT_TIMESTAMP, read_at TEXT
            );
            CREATE TABLE Notification (
              notification_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, message TEXT NOT NULL,
              notification_type TEXT, is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE Dispute (
              dispute_id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER NOT NULL, opened_by INTEGER NOT NULL,
              reason TEXT NOT NULL, description TEXT, status TEXT NOT NULL DEFAULT 'open', admin_id INTEGER,
              resolution TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT
            );
            INSERT INTO `User` (user_id,email,password_hash,full_name,role) VALUES
              (1,'client@example.test','x','Test Client','client'),
              (2,'freelancer@example.test','x','Test Freelancer','freelancer'),
              (3,'admin@example.test','x','Test Admin','admin'),
              (4,'freelancer2@example.test','x','Other Freelancer','freelancer');
            INSERT INTO Client (user_id, company_name) VALUES (1,'Test Co');
            INSERT INTO Freelancer (user_id, headline) VALUES (2,'Developer');
            INSERT INTO Freelancer (user_id, headline) VALUES (4,'Designer');
            INSERT INTO Skill (skill_id,name) VALUES (1,'Python'),(2,'MySQL');
            INSERT INTO Freelancer_Skill (freelancer_id,skill_id,proficiency_level) VALUES
              (2,1,5),(2,2,4),(4,2,5);
            INSERT INTO Category (category_id,name) VALUES (1,'Web Development');
            """
        )
        views_sql = (ROOT / "database" / "views.sql").read_text(encoding="utf-8")
        views_sql = re.sub(r"(?im)^USE\s+\w+\s*;\s*", "", views_sql)
        views_sql = views_sql.replace("CREATE OR REPLACE VIEW", "CREATE VIEW")
        self.raw.executescript(views_sql)

    def cursor(self, dictionary=False):
        return TestCursor(self, dictionary)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.db = TestConnection()
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "test-secret-key-0123456789abcdef",
            "JWT_SECRET_KEY": "test-jwt-secret-0123456789abcdef",
            "PASSWORD_RESET_DEV_MODE": True,
        })
        self.client = self.app.test_client()
        self.patches = [
            patch("app.utils.auth.get_db", return_value=self.db),
            patch("app.get_db", return_value=self.db),
            patch("app.routes.auth.get_db", return_value=self.db),
            patch("app.routes.users.get_db", return_value=self.db),
            patch("app.routes.profiles.get_db", return_value=self.db),
            patch("app.routes.projects.get_db", return_value=self.db),
            patch("app.routes.execution.get_db", return_value=self.db),
            patch("app.routes.payments.get_db", return_value=self.db),
            patch("app.routes.comms.get_db", return_value=self.db),
            patch("app.routes.skills.get_db", return_value=self.db),
            patch("app.routes.admin.get_db", return_value=self.db),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.db.raw.close()

    def token(self, user_id, role):
        with self.app.app_context():
            return create_access_token(identity=str(user_id), additional_claims={"role": role})

    def headers(self, user_id, role):
        return {"Authorization": f"Bearer {self.token(user_id, role)}"}

    def test_health_and_protected_route(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        for path, expected in (("/", b"FreelanceOS"), ("/app.js", None), ("/styles.css", None)):
            asset = self.client.get(path)
            self.assertEqual(asset.status_code, 200)
            if expected:
                self.assertIn(expected, asset.data)
            if path == "/":
                self.assertIn(b"forgotPasswordLink", asset.data)
                self.assertIn(b"forgotPasswordForm", asset.data)
                self.assertNotIn(b"API endpoint", asset.data)
                self.assertNotIn(b"apiBase", asset.data)
            asset.close()
        missing = self.client.get("/api/not-a-route")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json["error"]["code"], "not_found")

    def test_role_boundary(self):
        response = self.client.get("/api/freelancers/me", headers=self.headers(1, "client"))
        self.assertEqual(response.status_code, 403)

    def test_notification_endpoints_are_private_ordered_and_read_idempotent(self):
        self.assertEqual(self.client.get("/api/notifications").status_code, 401)
        self.assertEqual(self.client.patch("/api/notifications/1/read", json={}).status_code, 401)

        rows = [
            (1, "Earlier unread", "message_received", 0, "2026-10-25 09:00:00"),
            (1, "Latest unread", "task_submitted", 0, "2026-10-26 10:00:00"),
            (1, "Latest already read", "payment_completed", 1, "2026-10-26 10:00:00"),
            (2, "Other user's notice", "review_received", 0, "2026-10-26 11:00:00"),
        ]
        self.db.raw.executemany(
            "INSERT INTO Notification (user_id, message, notification_type, is_read, created_at) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self.db.raw.commit()
        user_one = self.headers(1, "client")
        user_two = self.headers(2, "freelancer")
        user_zero = self.headers(3, "admin")

        all_notices = self.client.get("/api/notifications", headers=user_one)
        self.assertEqual(all_notices.status_code, 200)
        self.assertEqual([n["message"] for n in all_notices.json["notifications"]], [
            "Latest already read", "Latest unread", "Earlier unread",
        ])
        unread = self.client.get("/api/notifications?unread_only=true&limit=1", headers=user_one)
        self.assertEqual([n["message"] for n in unread.json["notifications"]], ["Latest unread"])
        self.assertEqual(self.client.get("/api/notifications?unread_only=maybe", headers=user_one).status_code, 400)

        notification_id = all_notices.json["notifications"][1]["notification_id"]
        self.assertEqual(self.client.patch(f"/api/notifications/{notification_id}/read", headers=user_one, json={}).status_code, 200)
        # The endpoint is idempotent even when MySQL reports zero changed rows.
        self.assertEqual(self.client.patch(f"/api/notifications/{notification_id}/read", headers=user_one, json={}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/notifications/{notification_id}/read", headers=user_two, json={}).status_code, 404)
        self.assertEqual(self.client.get("/api/notifications", headers=user_two).json["notifications"][0]["message"], "Other user's notice")
        remaining = self.client.get("/api/notifications?unread_only=true", headers=user_one)
        self.assertEqual([n["message"] for n in remaining.json["notifications"]], ["Earlier unread"])

        marked = self.client.patch("/api/notifications/read-all", headers=user_one, json={})
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json["updated"], 1)
        self.assertEqual(self.client.get("/api/notifications?unread_only=true", headers=user_one).json["notifications"], [])
        self.assertEqual(self.client.patch("/api/notifications/read-all", headers=user_one, json={}).json["updated"], 0)
        self.assertEqual(self.client.get("/api/notifications", headers=user_zero).json["notifications"], [])
        self.assertEqual(self.client.patch("/api/notifications/read-all", headers=user_zero, json={}).json["updated"], 0)
        self.assertEqual(self.client.patch("/api/notifications/999/read", headers=user_one, json={}).status_code, 404)

    def test_notification_helper_validates_recipient_and_suppresses_retry_duplicates(self):
        cursor = self.db.cursor()
        self.assertTrue(add_notification(cursor, 2, "New event #41", "test_event"))
        self.assertFalse(add_notification(cursor, 2, "New event #41", "test_event"))
        with self.assertRaises(ValueError):
            add_notification(cursor, 999, "Invalid recipient", "test_event")
        self.db.commit()
        cursor.close()
        notices = self.client.get("/api/notifications", headers=self.headers(2, "freelancer")).json["notifications"]
        self.assertEqual(sum(n["message"] == "New event #41" for n in notices), 1)

    def test_project_and_application_notifications_are_automatic_and_targeted(self):
        client_headers = self.headers(1, "client")
        freelancer_headers = self.headers(2, "freelancer")
        other_freelancer_headers = self.headers(4, "freelancer")
        created = self.client.post("/api/projects", headers=client_headers, json={
            "title": "Python automation", "description": "Automate a reporting workflow.",
            "category_id": 1, "budget_min": 300, "budget_max": 700,
            "project_type": "fixed", "skill_ids": [1],
        })
        self.assertEqual(created.status_code, 201)
        project_id = created.json["project_id"]
        freelancer_notices = self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]
        self.assertEqual([n["notification_type"] for n in freelancer_notices], ["project_created"])
        self.assertIn(f"project #{project_id}", freelancer_notices[0]["message"])
        self.assertEqual(self.client.get("/api/notifications", headers=other_freelancer_headers).json["notifications"], [])
        self.assertEqual(self.client.get("/api/notifications", headers=client_headers).json["notifications"], [])

        bid = self.client.post(f"/api/projects/{project_id}/applications", headers=freelancer_headers, json={
            "proposal": "I can automate this workflow.", "bid_amount": 500, "estimated_days": 8,
        })
        self.assertEqual(bid.status_code, 201)
        client_notices = self.client.get("/api/notifications", headers=client_headers).json["notifications"]
        self.assertEqual([n["notification_type"] for n in client_notices], ["application_received"])
        self.assertIn(str(bid.json["application_id"]), client_notices[0]["message"])
        other_bid = self.client.post(f"/api/projects/{project_id}/applications", headers=other_freelancer_headers, json={
            "proposal": "I can also deliver this workflow.", "bid_amount": 550, "estimated_days": 9,
        })
        self.assertEqual(other_bid.status_code, 201)
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=client_headers).json["notifications"]].count("application_received"),
            2,
        )
        duplicate_bid = self.client.post(f"/api/projects/{project_id}/applications", headers=freelancer_headers, json={
            "proposal": "Retry should be rejected.", "bid_amount": 500, "estimated_days": 8,
        })
        self.assertEqual(duplicate_bid.status_code, 409)
        self.assertEqual(len(self.client.get("/api/notifications", headers=client_headers).json["notifications"]), 2)

        updated = self.client.patch(f"/api/projects/{project_id}", headers=client_headers, json={"budget_max": 800})
        self.assertEqual(updated.status_code, 200)
        freelancer_notices = self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]
        self.assertEqual([n["notification_type"] for n in freelancer_notices].count("project_updated"), 1)
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=other_freelancer_headers).json["notifications"]].count("project_updated"),
            1,
        )
        updated_again = self.client.patch(f"/api/projects/{project_id}", headers=client_headers, json={"budget_max": 800})
        self.assertEqual(updated_again.status_code, 200)
        self.assertEqual([n["notification_type"] for n in self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]].count("project_updated"), 1)

        accepted = self.client.patch(
            f"/api/applications/{bid.json['application_id']}/status", headers=client_headers,
            json={"status": "accepted"},
        )
        self.assertEqual(accepted.status_code, 200)
        freelancer_notices = self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]
        freelancer_types = [n["notification_type"] for n in freelancer_notices]
        self.assertIn("contract_created", freelancer_types)
        self.assertEqual(freelancer_types.count("application_status"), 1)
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=other_freelancer_headers).json["notifications"]].count("project_status_changed"),
            1,
        )
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=client_headers).json["notifications"]].count("application_received"),
            2,
        )
        rejected = self.client.patch(
            f"/api/applications/{other_bid.json['application_id']}/status", headers=client_headers,
            json={"status": "rejected"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertIn(
            "application_status",
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=other_freelancer_headers).json["notifications"]],
        )
        retry_accept = self.client.patch(
            f"/api/applications/{bid.json['application_id']}/status", headers=client_headers,
            json={"status": "accepted"},
        )
        self.assertEqual(retry_accept.status_code, 409)
        self.assertEqual(len(self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]), len(freelancer_notices))

        cancel_project = self.client.post("/api/projects", headers=client_headers, json={
            "title": "Cancel notification example", "description": "A pending project cancellation test.",
            "category_id": 1, "budget_min": 100, "budget_max": 250,
            "project_type": "fixed", "skill_ids": [2],
        })
        self.assertEqual(cancel_project.status_code, 201)
        cancel_project_id = cancel_project.json["project_id"]
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=other_freelancer_headers).json["notifications"]].count("project_created"),
            1,
        )
        cancel_bid = self.client.post(f"/api/projects/{cancel_project_id}/applications", headers=other_freelancer_headers, json={
            "proposal": "I can take this project.", "bid_amount": 200, "estimated_days": 5,
        })
        self.assertEqual(cancel_bid.status_code, 201)
        client_before_cancel = len(self.client.get("/api/notifications", headers=client_headers).json["notifications"])
        self.assertEqual(self.client.delete(f"/api/projects/{cancel_project_id}", headers=client_headers).status_code, 200)
        other_types = [n["notification_type"] for n in self.client.get("/api/notifications", headers=other_freelancer_headers).json["notifications"]]
        self.assertEqual(other_types.count("project_status_changed"), 2)
        self.assertEqual(len(self.client.get("/api/notifications", headers=client_headers).json["notifications"]), client_before_cancel)
        self.assertEqual(self.client.delete(f"/api/projects/{cancel_project_id}", headers=client_headers).status_code, 404)

        draft = self.client.post("/api/projects", headers=client_headers, json={
            "title": "Publish notification example", "description": "A draft that will be published.",
            "category_id": 1, "budget_min": 100, "budget_max": 250,
            "project_type": "fixed", "status": "draft", "skill_ids": [1],
        })
        self.assertEqual(draft.status_code, 201)
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]].count("project_created"),
            2,
        )
        published = self.client.patch(f"/api/projects/{draft.json['project_id']}", headers=client_headers, json={"status": "open"})
        self.assertEqual(published.status_code, 200)
        self.assertIn(
            "project_status_changed",
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]],
        )

    def test_notification_failure_rolls_back_project_creation(self):
        before_projects = self.db.raw.execute("SELECT COUNT(*) FROM Project").fetchone()[0]
        before_notifications = self.db.raw.execute("SELECT COUNT(*) FROM Notification").fetchone()[0]
        payload = {
            "title": "Rollback notification test", "description": "This project must not persist.",
            "category_id": 1, "budget_min": 100, "budget_max": 200,
            "project_type": "fixed", "skill_ids": [1],
        }
        with patch("app.utils.notifications.add_notification", side_effect=RuntimeError("simulated notification insert failure")):
            failed = self.client.post("/api/projects", headers=self.headers(1, "client"), json=payload)
        self.assertEqual(failed.status_code, 500)
        after_projects = self.db.raw.execute("SELECT COUNT(*) FROM Project").fetchone()[0]
        self.assertEqual(after_projects, before_projects)
        after_notifications = self.db.raw.execute("SELECT COUNT(*) FROM Notification").fetchone()[0]
        self.assertEqual(after_notifications, before_notifications)

    def test_client_profile_read_and_update(self):
        headers = self.headers(1, "client")
        response = self.client.patch("/api/clients/me", headers=headers, json={"company_name": "Northstar"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/api/clients/me", headers=headers)
        self.assertEqual(response.json["profile"]["company_name"], "Northstar")

    def test_freelancer_profile_and_skills(self):
        headers = self.headers(2, "freelancer")
        response = self.client.patch("/api/freelancers/me", headers=headers, json={"hourly_rate": 45, "experience_years": 4})
        self.assertEqual(response.status_code, 200)
        response = self.client.put(
            "/api/skills/me", headers=headers,
            json={"skills": [{"skill_id": 1, "proficiency_level": 5}, {"skill_id": 2, "proficiency_level": 3}]},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/api/skills/me", headers=headers)
        self.assertEqual([item["name"] for item in response.json["skills"]], ["MySQL", "Python"])

    def test_invalid_profile_and_skill_payloads(self):
        response = self.client.patch("/api/freelancers/me", headers=self.headers(2, "freelancer"), json={"role": "admin"})
        self.assertEqual(response.status_code, 400)
        response = self.client.put("/api/skills/me", headers=self.headers(2, "freelancer"), json={"skills": [{"skill_id": 1, "proficiency_level": 6}]})
        self.assertEqual(response.status_code, 400)

    def test_admin_user_management_and_skill_catalog(self):
        headers = self.headers(3, "admin")
        response = self.client.get("/api/users?role=freelancer", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["users"]), 2)
        response = self.client.patch("/api/users/2/status", headers=headers, json={"account_status": "suspended"})
        self.assertEqual(response.status_code, 200)
        suspended = self.client.get("/api/freelancers/me", headers=self.headers(2, "freelancer"))
        self.assertEqual(suspended.status_code, 401)
        response = self.client.post("/api/skills", headers=headers, json={"name": "Flask"})
        self.assertEqual(response.status_code, 201)
        duplicate = self.client.post("/api/skills", headers=headers, json={"name": "Flask"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(len(self.client.get("/api/skills").json["skills"]), 3)

    def test_admin_reports_are_protected_and_validated(self):
        admin = self.headers(3, "admin")
        self.assertEqual(self.client.get("/api/admin/reports/summary", headers=self.headers(1, "client")).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/disputes?limit=0", headers=admin).status_code, 400)
        report = self.client.get("/api/admin/reports/summary", headers=admin)
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json["report"]["user_count"], 4)
        self.assertEqual(report.json["report"]["project_count"], 0)
        self.assertEqual(self.client.get("/api/admin/reports/earnings", headers=admin).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/reports/spending", headers=admin).status_code, 200)

    def test_category_catalog_is_database_backed_and_public(self):
        response = self.client.get("/api/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["categories"], [{"category_id": 1, "name": "Web Development", "description": None}])

    def test_admin_cannot_suspend_itself(self):
        response = self.client.patch(
            "/api/users/3/status", headers=self.headers(3, "admin"), json={"account_status": "suspended"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"]["code"], "self_lockout_prevented")

    def test_portfolio_owner_isolation(self):
        headers = self.headers(2, "freelancer")
        created = self.client.post("/api/freelancers/me/portfolio", headers=headers, json={"title": "Example"})
        self.assertEqual(created.status_code, 201)
        item_id = created.json["portfolio_id"]
        outsider = self.client.delete(f"/api/freelancers/me/portfolio/{item_id}", headers=self.headers(4, "freelancer"))
        self.assertEqual(outsider.status_code, 404)

    def test_registration_and_login(self):
        response = self.client.post("/api/auth/register", json={
            "email": "new@example.test", "full_name": "New Client", "password": "secret123", "role": "client"
        })
        self.assertEqual(response.status_code, 201)
        response = self.client.post("/api/auth/login", json={"email": "new@example.test", "password": "secret123"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.json)
        duplicate = self.client.post("/api/auth/register", json={
            "email": "new@example.test", "full_name": "Duplicate", "password": "secret123", "role": "client"
        })
        self.assertEqual(duplicate.status_code, 409)

    def test_simple_forgot_password_resets_password_and_allows_login(self):
        self.db.raw.execute(
            "UPDATE `User` SET password_hash = ? WHERE user_id = ?",
            (generate_password_hash("old-password-123"), 1),
        )
        reset = self.client.post("/api/auth/forgot-password", json={
            "email": "CLIENT@example.test", "new_password": "new-secret-123",
        })
        self.assertEqual(reset.status_code, 200)
        self.assertNotIn("token", reset.json)
        stored = self.db.raw.execute("SELECT password_hash FROM `User` WHERE user_id = 1").fetchone()[0]
        self.assertNotEqual(stored, "new-secret-123")
        old_login = self.client.post("/api/auth/login", json={"email": "client@example.test", "password": "old-password-123"})
        self.assertEqual(old_login.status_code, 401)
        login = self.client.post("/api/auth/login", json={"email": "client@example.test", "password": "new-secret-123"})
        self.assertEqual(login.status_code, 200)

    def test_simple_forgot_password_is_generic_and_development_only(self):
        missing = self.client.post("/api/auth/forgot-password", json={
            "email": "missing@example.test", "new_password": "new-secret-123",
        })
        existing = self.client.post("/api/auth/forgot-password", json={
            "email": "client@example.test", "new_password": "new-secret-123",
        })
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(existing.status_code, 200)
        self.assertEqual(missing.json["error"]["message"], "Unable to reset the password. Check the email and try again.")
        self.assertNotIn("not registered", missing.json["error"]["message"].lower())

        remote = self.client.post(
            "/api/auth/forgot-password", json={"email": "client@example.test", "new_password": "new-secret-123"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.10"},
        )
        self.assertEqual(remote.status_code, 403)
        short = self.client.post("/api/auth/forgot-password", json={"email": "client@example.test", "new_password": "short"})
        self.assertEqual(short.status_code, 400)
        invalid_email = self.client.post("/api/auth/forgot-password", json={"email": "not-an-email", "new_password": "long-enough-password"})
        self.assertEqual(invalid_email.status_code, 400)

    def test_logout_persists_token_revocation(self):
        token = self.token(1, "client")
        headers = {"Authorization": f"Bearer {token}"}
        logged_out = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(logged_out.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        response = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"]["code"], "revoked_token")
        restarted_app = create_app({"TESTING": True, "SECRET_KEY": "test-secret-key-0123456789abcdef", "JWT_SECRET_KEY": "test-jwt-secret-0123456789abcdef"})
        restarted_client = restarted_app.test_client()
        restarted_response = restarted_client.get("/api/auth/me", headers=headers)
        self.assertEqual(restarted_response.status_code, 401)
        self.assertEqual(restarted_response.json["error"]["code"], "revoked_token")

    def test_project_create_search_and_owner_listing(self):
        client_headers = self.headers(1, "client")
        created = self.client.post("/api/projects", headers=client_headers, json={
            "title": "Build a tracker", "description": "A small project tracking tool.",
            "category_id": 1, "budget_min": 500, "budget_max": 900,
            "project_type": "fixed", "deadline": "2026-12-15", "skill_ids": [1, 2],
        })
        self.assertEqual(created.status_code, 201)
        project_id = created.json["project_id"]
        self.assertEqual(self.client.get("/api/projects/999999").status_code, 404)
        missing_project_fields = self.client.post("/api/projects", headers=client_headers, json={"title": "Incomplete"})
        self.assertEqual(missing_project_fields.status_code, 400)
        wrong_role_create = self.client.post("/api/projects", headers=self.headers(2, "freelancer"), json={})
        self.assertEqual(wrong_role_create.status_code, 403)
        found = self.client.get("/api/projects?skill_id=1&skill_id=2&budget_min=600")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json["projects"][0]["project_id"], project_id)
        self.assertEqual(len(found.json["projects"][0]["required_skills"]), 2)
        mine = self.client.get("/api/projects/mine", headers=client_headers)
        self.assertEqual(len(mine.json["projects"]), 1)

    def test_project_update_cancel_and_private_detail(self):
        headers = self.headers(1, "client")
        created = self.client.post("/api/projects", headers=headers, json={
            "title": "Private draft", "description": "Draft description", "category_id": 1,
            "budget_min": 100, "budget_max": 200, "project_type": "hourly", "status": "draft",
        })
        project_id = created.json["project_id"]
        self.assertEqual(self.client.get(f"/api/projects/{project_id}").status_code, 404)
        updated = self.client.patch(f"/api/projects/{project_id}", headers=headers, json={"budget_min": 150})
        self.assertEqual(updated.status_code, 200)
        canceled = self.client.delete(f"/api/projects/{project_id}", headers=headers)
        self.assertEqual(canceled.status_code, 200)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}").status_code, 404)

    def test_application_bid_and_client_decision(self):
        created = self.client.post("/api/projects", headers=self.headers(1, "client"), json={
            "title": "API work", "description": "Implement a small API.", "category_id": 1,
            "budget_min": 300, "budget_max": 600, "project_type": "fixed",
        })
        project_id = created.json["project_id"]
        freelancer_headers = self.headers(2, "freelancer")
        bid = self.client.post(f"/api/projects/{project_id}/applications", headers=freelancer_headers, json={
            "proposal": "I can deliver this project.", "bid_amount": 450, "estimated_days": 14,
        })
        self.assertEqual(bid.status_code, 201)
        client_headers = self.headers(1, "client")
        self.assertEqual(
            [n["notification_type"] for n in self.client.get("/api/notifications", headers=client_headers).json["notifications"]],
            ["application_received"],
        )
        application_id = bid.json["application_id"]
        duplicate_bid = self.client.post(f"/api/projects/{project_id}/applications", headers=freelancer_headers, json={
            "proposal": "Duplicate bid.", "bid_amount": 460, "estimated_days": 15,
        })
        self.assertEqual(duplicate_bid.status_code, 409)
        self.assertEqual(self.client.get("/api/applications/mine", headers=freelancer_headers).status_code, 200)
        applications = self.client.get(f"/api/projects/{project_id}/applications", headers=client_headers)
        self.assertEqual(len(applications.json["applications"]), 1)
        shortlisted = self.client.patch(f"/api/applications/{application_id}/status", headers=client_headers, json={"status": "shortlisted"})
        self.assertEqual(shortlisted.status_code, 200)
        client_notices = self.client.get("/api/notifications", headers=client_headers).json["notifications"]
        self.assertEqual([n["notification_type"] for n in client_notices], ["application_received"])
        accepted = self.client.patch(f"/api/applications/{application_id}/status", headers=client_headers, json={"status": "accepted"})
        self.assertEqual(accepted.status_code, 200)
        contract_id = accepted.json["contract_id"]
        freelancer_notice_types = [n["notification_type"] for n in self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]]
        self.assertEqual(freelancer_notice_types.count("application_status"), 2)
        self.assertEqual(freelancer_notice_types.count("contract_created"), 1)
        self.assertEqual([n["notification_type"] for n in self.client.get("/api/notifications", headers=client_headers).json["notifications"]], ["application_received"])
        active_review = self.client.post(
            f"/api/contracts/{contract_id}/reviews", headers=client_headers, json={"rating": 5},
        )
        self.assertEqual(active_review.status_code, 409)
        project = self.client.get(f"/api/projects/{project_id}", headers=client_headers)
        self.assertEqual(project.json["project"]["status"], "in_progress")
        contract = self.client.get(f"/api/contracts/{contract_id}", headers=client_headers)
        self.assertEqual(contract.status_code, 200)
        self.assertEqual(contract.json["contract"]["agreed_amount"], 450)

        opened = self.client.post(
            f"/api/contracts/{contract_id}/disputes", headers=client_headers,
            json={"reason": "Scope clarification", "description": "Confirm acceptance criteria."},
        )
        self.assertEqual(opened.status_code, 201)
        dispute_id = opened.json["dispute_id"]
        outsider = self.client.post(
            f"/api/contracts/{contract_id}/disputes", headers=self.headers(4, "freelancer"),
            json={"reason": "Unrelated account"},
        )
        self.assertEqual(outsider.status_code, 404)
        self.assertEqual(self.client.post(
            f"/api/contracts/{contract_id}/disputes", headers=client_headers, json={"reason": " "},
        ).status_code, 400)
        admin_headers = self.headers(3, "admin")
        self.assertEqual(self.client.get("/api/admin/disputes", headers=client_headers).status_code, 403)
        admin_disputes = self.client.get("/api/admin/disputes?status=open", headers=admin_headers)
        self.assertEqual(admin_disputes.status_code, 200)
        self.assertEqual(admin_disputes.json["disputes"][0]["dispute_id"], dispute_id)
        self.assertEqual(self.client.patch(
            f"/api/admin/disputes/{dispute_id}", headers=admin_headers, json={"status": "resolved"},
        ).status_code, 400)
        self.assertEqual(self.client.patch(
            f"/api/admin/disputes/{dispute_id}", headers=admin_headers, json={"status": "investigating"},
        ).status_code, 200)
        self.assertEqual(self.client.patch(
            f"/api/admin/disputes/{dispute_id}", headers=admin_headers,
            json={"status": "resolved", "resolution": "Scope confirmed by both parties."},
        ).status_code, 200)
        mine = self.client.get("/api/disputes/mine", headers=self.headers(2, "freelancer"))
        self.assertEqual(mine.json["disputes"][0]["status"], "resolved")

        task_response = self.client.post(f"/api/contracts/{contract_id}/tasks", headers=client_headers, json={
            "title": "Build first endpoint", "description": "Implement and document the endpoint.", "due_date": "2026-10-15",
        })
        self.assertEqual(task_response.status_code, 201)
        task_id = task_response.json["task_id"]
        self.assertEqual(task_response.json["assigned_to"], 2)
        freelancer_headers = self.headers(2, "freelancer")
        progress = self.client.patch(f"/api/tasks/{task_id}", headers=freelancer_headers, json={"status": "in_progress"})
        self.assertEqual(progress.status_code, 200)
        submitted = self.client.patch(f"/api/tasks/{task_id}", headers=freelancer_headers, json={"status": "submitted"})
        self.assertEqual(submitted.status_code, 200)
        completed = self.client.patch(f"/api/tasks/{task_id}", headers=client_headers, json={"status": "completed"})
        self.assertEqual(completed.status_code, 200)

        milestone_response = self.client.post(f"/api/contracts/{contract_id}/milestones", headers=client_headers, json={
            "title": "Initial delivery", "description": "First working version.", "amount": 200,
        })
        self.assertEqual(milestone_response.status_code, 201)
        over_budget = self.client.post(f"/api/contracts/{contract_id}/milestones", headers=client_headers, json={
            "title": "Over budget", "amount": 300,
        })
        self.assertEqual(over_budget.status_code, 409)
        milestone_id = milestone_response.json["milestone_id"]
        submitted_milestone = self.client.patch(f"/api/milestones/{milestone_id}/submit", headers=freelancer_headers, json={})
        self.assertEqual(submitted_milestone.status_code, 200)
        reviewed = self.client.patch(f"/api/milestones/{milestone_id}/review", headers=client_headers, json={"status": "approved"})
        self.assertEqual(reviewed.status_code, 200)

        payment_response = self.client.post(f"/api/contracts/{contract_id}/payments", headers=client_headers, json={
            "milestone_id": milestone_id, "amount": 200, "payment_method": "demo",
        })
        self.assertEqual(payment_response.status_code, 201)
        exceeds_milestone = self.client.post(f"/api/contracts/{contract_id}/payments", headers=client_headers, json={
            "milestone_id": milestone_id, "amount": 1,
        })
        self.assertEqual(exceeds_milestone.status_code, 409)
        payment_id = payment_response.json["payment_id"]
        self.assertEqual(self.client.get(f"/api/payments/{payment_id}", headers=client_headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/payments/{payment_id}", headers=self.headers(4, "freelancer")).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/payments/{payment_id}/status", headers=client_headers, json={"status": "completed"}).status_code, 403)
        invalid_transition = self.client.patch(f"/api/payments/{payment_id}/status", headers=admin_headers, json={"status": "refunded"})
        self.assertEqual(invalid_transition.status_code, 409)
        self.assertEqual(len(self.client.get("/api/payments/mine", headers=client_headers).json["payments"]), 1)
        self.assertEqual(len(self.client.get("/api/payments/mine", headers=freelancer_headers).json["payments"]), 1)
        processing = self.client.patch(f"/api/payments/{payment_id}/status", headers=admin_headers, json={"status": "processing"})
        self.assertEqual(processing.status_code, 200)
        settled = self.client.patch(
            f"/api/payments/{payment_id}/status", headers=admin_headers,
            json={"status": "completed", "transaction_reference": "TEST-TRANSFER-01"},
        )
        self.assertEqual(settled.status_code, 200)
        self.assertEqual(self.client.get(f"/api/contracts/{contract_id}/milestones", headers=client_headers).json["milestones"][0]["status"], "paid")
        remaining_payment = self.client.post(f"/api/contracts/{contract_id}/payments", headers=client_headers, json={"amount": 250})
        self.assertEqual(remaining_payment.status_code, 201)
        self.assertEqual(self.client.patch(
            f"/api/payments/{remaining_payment.json['payment_id']}/status", headers=admin_headers,
            json={"status": "completed", "transaction_reference": "TEST-TRANSFER-02"},
        ).status_code, 200)
        self.assertEqual(len(self.client.get("/api/payments/mine", headers=client_headers).json["payments"]), 2)

        completed_contract = self.client.post(f"/api/contracts/{contract_id}/complete", headers=client_headers)
        self.assertEqual(completed_contract.status_code, 200)
        client_review = self.client.post(f"/api/contracts/{contract_id}/reviews", headers=client_headers, json={"rating": 5, "comment": "Excellent delivery."})
        self.assertEqual(client_review.status_code, 201)
        freelancer_review = self.client.post(f"/api/contracts/{contract_id}/reviews", headers=freelancer_headers, json={"rating": 4})
        self.assertEqual(freelancer_review.status_code, 201)
        duplicate_review = self.client.post(f"/api/contracts/{contract_id}/reviews", headers=client_headers, json={"rating": 4})
        self.assertEqual(duplicate_review.status_code, 409)
        rating = self.client.get("/api/reviews/users/2")
        self.assertEqual(rating.json["summary"]["review_count"], 1)
        view_cursor = self.db.cursor(dictionary=True)
        view_cursor.execute("SELECT * FROM v_user_rating_summary WHERE user_id = %s", (2,))
        self.assertEqual(view_cursor.fetchone()["average_rating"], 5)
        view_cursor.execute("SELECT * FROM v_contract_payment_summary WHERE contract_id = %s", (contract_id,))
        self.assertEqual(view_cursor.fetchone()["completed_amount"], 450)
        view_cursor.execute("SELECT * FROM v_freelancer_earnings WHERE freelancer_id = %s", (2,))
        self.assertEqual(view_cursor.fetchone()["total_earnings"], 450)
        view_cursor.execute("SELECT * FROM v_client_spending WHERE client_id = %s", (1,))
        self.assertEqual(view_cursor.fetchone()["total_spending"], 450)
        view_cursor.close()
        admin_report = self.client.get("/api/admin/reports/summary", headers=admin_headers)
        self.assertEqual(admin_report.status_code, 200)
        self.assertEqual(admin_report.json["report"]["completed_payment_volume"], 450)
        self.assertEqual(admin_report.json["report"]["project_count"], 1)
        self.assertEqual(self.client.get("/api/admin/reports/earnings", headers=admin_headers).json["earnings"][0]["total_earnings"], 450)
        self.assertEqual(self.client.get("/api/admin/reports/spending", headers=admin_headers).json["spending"][0]["total_spending"], 450)

        message = self.client.post(f"/api/contracts/{contract_id}/messages", headers=client_headers, json={"body": "Thanks for the delivery."})
        self.assertEqual(message.status_code, 201)
        forged = self.client.post(f"/api/contracts/{contract_id}/messages", headers=client_headers, json={"body": "Forged sender", "sender_id": 2})
        self.assertEqual(forged.status_code, 400)
        outsider_messages = self.client.get(f"/api/contracts/{contract_id}/messages", headers=self.headers(4, "freelancer"))
        self.assertEqual(outsider_messages.status_code, 404)
        messages = self.client.get(f"/api/contracts/{contract_id}/messages", headers=freelancer_headers)
        self.assertEqual(len(messages.json["messages"]), 1)
        read = self.client.patch(f"/api/messages/{message.json['message_id']}/read", headers=freelancer_headers)
        self.assertEqual(read.status_code, 200)
        client_notices = self.client.get("/api/notifications", headers=client_headers).json["notifications"]
        client_types = [n["notification_type"] for n in client_notices]
        self.assertIn("task_submitted", client_types)
        self.assertIn("milestone_submitted", client_types)
        self.assertIn("payment_completed", client_types)
        self.assertIn("review_received", client_types)
        self.assertIn("dispute_status", client_types)
        self.assertIn("task_updated", client_types)
        self.assertNotIn("dispute_opened", client_types)
        freelancer_notices = self.client.get("/api/notifications", headers=freelancer_headers).json["notifications"]
        freelancer_types = [n["notification_type"] for n in freelancer_notices]
        for expected_type in (
            "task_assigned", "task_completed", "milestone_added", "milestone_approved",
            "payment_pending", "payment_processing", "payment_completed", "contract_completed",
            "review_received", "message_received", "dispute_opened", "dispute_status",
        ):
            self.assertIn(expected_type, freelancer_types)
        admin_types = [n["notification_type"] for n in self.client.get("/api/notifications", headers=admin_headers).json["notifications"]]
        self.assertEqual(admin_types.count("dispute_opened"), 1)
        self.assertEqual(freelancer_types.count("message_received"), 1)
        notices = self.client.get("/api/notifications?unread_only=true", headers=freelancer_headers)
        self.assertGreater(len(notices.json["notifications"]), 0)
        notice_id = notices.json["notifications"][0]["notification_id"]
        self.assertEqual(self.client.patch(f"/api/notifications/{notice_id}/read", headers=freelancer_headers).status_code, 200)
        self.assertEqual(self.client.patch("/api/notifications/read-all", headers=freelancer_headers).status_code, 200)

        unavailable = self.client.post(f"/api/projects/{project_id}/applications", headers=self.headers(4, "freelancer"), json={
            "proposal": "Another bid.", "bid_amount": 500, "estimated_days": 10,
        })
        self.assertEqual(unavailable.status_code, 404)


if __name__ == "__main__":
    unittest.main()
