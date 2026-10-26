# Freelancer Project Management System

A college DBMS project for managing freelance projects from discovery and bidding through hiring, delivery, payment records, reviews, and administration.

## Features

- Client and freelancer registration, JWT login/logout, role checks, local demo password reset, profiles, skills, and portfolio.
- Project creation, search/filter/sort, required skills, freelancer applications/bids, and client shortlist/accept/reject.
- Contracts, tasks, milestones, payment ledger, reviews, messaging, notifications, and disputes.
- Role dashboards and admin controls/reports for users, payments, projects, and disputes.
- Payment operations record application state only; this project does not connect to a payment processor or transfer funds.

## Tech stack

HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js, Python, Flask REST API, Flask-JWT-Extended, MySQL 8.0.16+, and mysql-connector-python. The frontend is served by Flask; Bootstrap and Chart.js are loaded from jsDelivr. No separate frontend build is required.

## Clean setup (Windows PowerShell)

Requirements: Python 3.10+, MySQL 8.0.16+ (CHECK constraints are enforced), and the MySQL command-line client on PATH.

1. From the repository root, create the database objects in order:

   ```powershell
   mysql -u root -p --execute="source database/schema.sql"
   mysql -u root -p --execute="source database/seed.sql"
   mysql -u root -p --execute="source database/triggers.sql"
   mysql -u root -p --execute="source database/views.sql"
   mysql -u root -p --execute="source database/routines.sql"
   ```

   `seed.sql` is a rerunnable local/demo data load. It replaces the named demo workflows and refreshes the documented demo accounts; use it only in a college/demo database, not a production database. Omit it if you want an empty database. On an existing database from the earlier reset-token implementation, apply `database/migrations/001_remove_unused_password_reset_tokens.sql` once to remove its unused token table and add the completed-payment check. Re-run `database/triggers.sql` to install the current payment rules. `phase11_indexes.sql` is only for an existing database that predates the index now included in `schema.sql`.

2. Create a Python environment and install dependencies:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   cd ..
   ```

3. Copy `.env.example` to `.env` in the repository root. Set the MySQL account/database values. No SMTP configuration is used. Generate distinct application secrets:

   ```powershell
   py -c "import secrets; print(secrets.token_hex(32))"
   ```

   Run that command twice and use the two outputs for `FLASK_SECRET_KEY` and `JWT_SECRET_KEY`. Keep `.env` private and out of version control.

4. Start Flask:

   ```powershell
   cd backend
   python run.py
   ```

   Open [http://127.0.0.1:5000](http://127.0.0.1:5000). `GET /api/health` checks API availability without requiring a database connection.

5. Run the API suite from `backend/`:

   ```powershell
   python -m unittest discover -s tests -v
   ```

The suite uses a SQLite test double for API behavior and reporting views; it does not replace a live MySQL install check. The seed provides six local demo accounts: `client@example.test`, `client2@example.test`, `freelancer@example.test`, `freelancer2@example.test`, `freelancer3@example.test`, and `admin@example.test`. Their shared demo password is `Demo@123`; the database stores Werkzeug hashes, not plaintext passwords. Do not reuse these credentials outside a local demonstration. Public registration creates client/freelancer accounts; create a separate administrator account directly in MySQL if needed. The simple demo password reset accepts an email and a new password without proving email ownership. It is loopback-only and must have `PASSWORD_RESET_DEV_MODE=true`; keep the flag false outside local development.

## Project layout

```text
backend/app/          Flask factory, configuration, DB helper, errors, routes, auth utilities
backend/tests/        API tests (SQLite test double)
database/             MySQL schema, sample data, triggers, views, routines, DBMS review and viva queries
frontend/             Static HTML/CSS/JavaScript interface
.env.example          Environment variable template; copy to an ignored .env
```

## Database structure

The schema is defined in [`database/schema.sql`](database/schema.sql). Main entities are `User`, role-specific `Client` and `Freelancer` profiles, `Skill`, `Category`, `Project`, `Application`, `Contract`, `Task`, `Milestone`, `Payment`, `Review`, `Message`, `Notification`, `Portfolio`, and `Dispute`; `Freelancer_Skill` and `Project_Skill` resolve many-to-many relationships. `Revoked_Token` persists JWT logout revocations.

- **1:1:** `User` to its `Client` or `Freelancer` profile (profile PK is also an FK).
- **1:M:** client to projects; project to applications; accepted application/project to contract; contract to tasks, milestones, payments, reviews, messages, and disputes; user to notifications.
- **M:N:** freelancers to skills and projects to required skills, through composite-key junction tables.
- FKs, unique keys, checks, defaults, and indexes enforce ownership, allowed states, valid amounts/ratings, uniqueness, and common lookup paths.

The entity and junction core is normalized to 3NF. A documented caveat is that some event/ledger fields (`Task.assigned_to`, payment parties, and message receiver) repeat facts derivable from a contract. Password reset does not use tokens, token tables, links, or email. See [`database/DBMS_REVIEW.md`](database/DBMS_REVIEW.md) for the detailed normalization and integrity review, and [`database/viva_queries.sql`](database/viva_queries.sql) for safe demonstration queries.

## API guide

All routes are under `/api`. Protected requests use `Authorization: Bearer <access-token>`. User registration permits `client` and `freelancer`; admin routes require an existing admin account. Route groups and key operations:

| Area | Main routes | Access |
|---|---|---|
| Health/auth | `GET /health`, `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/forgot-password`, `GET /auth/me` | Forgot-password demo reset is local-only and requires the development flag |
| Users/profiles/skills | `/users/me`, `/clients/me`, `/freelancers/me`, `/freelancers/me/portfolio`, `/skills`, `/skills/me` | Self/role; user and skill administration is admin-only |
| Projects/applications | `GET/POST /projects`, `/projects/<id>`, `/projects/<id>/applications`, `/applications/mine`, `/applications/<id>/status` | Public browse; client owns projects and decisions; freelancer bids |
| Hiring/execution | `/contracts/mine`, `/contracts/<id>`, `/contracts/<id>/tasks`, `/tasks/<id>`, `/contracts/<id>/milestones`, `/milestones/<id>/submit`, `/milestones/<id>/review` | Contract participants; client/freelancer actions are role-checked |
| Payments | `/contracts/<id>/payments`, `/payments/mine`, `/payments/<id>`, `/payments/<id>/status` | Participants read/create; admin updates status |
| Reviews/comms | `/contracts/<id>/reviews`, `/reviews/users/<id>`, `/contracts/<id>/messages`, `/messages/<id>/read`, `/notifications` | Contract participants / authenticated user |
| Disputes/admin | `/contracts/<id>/disputes`, `/disputes/mine`, `/admin/disputes`, `/admin/reports/*`, `/users`, `/users/<id>/status` | Participants open/read own; admin manages and reports |

Request/response validation and required fields are defined in the route modules under [`backend/app/routes`](backend/app/routes). The DBMS objects are in `database/triggers.sql`, `views.sql`, and `routines.sql`; DBMS objects are not HTTP APIs.

`GET /api/categories` returns the database-backed category catalog used by project forms and search filters. Payment status actions only update the demo ledger; no money is transferred.

The basic local demo reset uses `POST /api/auth/forgot-password` with `{"email":"you@example.com","new_password":"at-least-8-characters"}`. The login-page form also asks for password confirmation. No email, SMTP, OTP, reset link, or token is used. The endpoint returns a generic error for unknown or inactive accounts, hashes the password with Werkzeug, and only updates active accounts when `PASSWORD_RESET_DEV_MODE=true` and the request is from loopback. This demo flow does not verify email ownership and must not be enabled on a public deployment.

## DBMS concepts demonstrated

Primary/foreign/composite keys; UNIQUE, NOT NULL, CHECK, DEFAULT and referential actions; 1NF/2NF/3NF discussion; parameterized SQL; joins; subqueries and `EXISTS`; aggregates with `GROUP BY`/`HAVING`; indexes; reporting views; stored procedures and functions; triggers; and transactional application acceptance, task/milestone workflows, and payment updates. The detailed map and verification limits are in [`database/DBMS_REVIEW.md`](database/DBMS_REVIEW.md).

## Known verification limits

The automated API tests use SQLite and do not verify MySQL-specific DDL, CHECK/FK enforcement, triggers, stored procedures/functions, or execution plans. Run the SQL scripts against MySQL 8.0.16+ for those checks. External CDN assets require internet access. Seeded accounts cannot authenticate until their placeholder password hashes are replaced.
