# DBMS Review

## Normalization

- **1NF:** columns hold scalar values; skills are represented through `Skill`, `Freelancer_Skill`, and `Project_Skill`, not comma-separated lists.
- **2NF:** the composite-key bridge tables have no partial non-key dependencies. `Freelancer_Skill.proficiency_level` depends on the full `(freelancer_id, skill_id)` key. Other tables use a single-column primary key or have no non-key attributes.
- **3NF:** core entities and junction relations are separated; category/skill names and report aggregates are not copied into dependent rows. There is a **strict 3NF caveat** in event rows: `Task.assigned_to` is determined by its contract; payment parties are determined by the contract; and a message receiver is determined by `(contract_id, sender_id)`. These are deliberately retained as event/authorization/ledger fields to preserve the current API shape and direct participant history. FKs protect referenced users/contracts, task assignment is also checked by triggers, and payment creation derives its parties from the contract in the API. Thus the entity/junction core is 3NF, while the event tables include controlled denormalization; a strict all-relations 3NF requirement would need those values derived through joins or represented with separate participant/assignment relations.

## Keys, constraints, and relationships

- Each entity table has a primary key; `Freelancer_Skill` and `Project_Skill` use composite primary keys.
- Foreign keys enforce profile ownership, project/client/category links, applications, contract/application/project consistency, task/milestone/payment ownership, and review/message/notification/dispute references.
- Unique constraints cover user email, skill/category names, one bid per freelancer/project, one contract per project/application, milestone titles per contract, transaction references, and one review per reviewer/contract.
- Required fields use `NOT NULL`; status, role, numeric range, rating, proficiency, and party-separation rules use `CHECK`; lifecycle fields use defaults for status and timestamps.
- `CASCADE` is used for dependent profiles and bridge rows; financial and historical relationships use `RESTRICT` so ledger/history is not silently deleted.
- 1:1: `User` to `Client` or `Freelancer` through profile PK/FKs. 1:M: client/project, project/application, contract/task/milestone/payment/message, and user/notification. M:N: freelancer/skill and project/skill through bridge tables.
- Password reset is a loopback-only demo operation that updates the Werkzeug hash directly; it uses no token table, reset link, OTP, or email.

## Queries, objects, and indexing

- Route SQL demonstrates joins in project/application/contract/payment/review lookups, grouped aggregates in reporting views and admin reports, `HAVING` and `EXISTS` for all-required-skill matching, and parameterized subqueries for search.
- Reporting views summarize contract payments, freelancer earnings, client spending, and user ratings. Functions calculate average rating and contract balance. Procedures demonstrate transactional hiring and milestone settlement. Triggers enforce accepted-application contract creation, hired-freelancer task assignment, contract payment-party matching, and valid payment status transitions.
- Existing indexes cover ownership/status/date access paths, bridge-table reverse lookup, unread notifications/messages, disputes, and transaction references. Added `ix_payment_milestone_status` for frequent milestone payment reservation and settlement lookups. See `phase11_indexes.sql` to apply it once to an existing database.
- `viva_queries.sql` contains read-focused examples for joins, aggregation, `HAVING`, subqueries, views, functions, transaction locking/rollback, triggers, and indexes. Mutating stored procedure examples are commented out.

## Verification limits

The API integration suite executes route SQL and reporting views against the SQLite test double. No MySQL client is installed in the current environment, so MySQL-only DDL, triggers, procedures/functions, foreign-key behavior, and `EXPLAIN` plans still need to be run on MySQL 8.0.16+ after applying `schema.sql`, `seed.sql`, `triggers.sql`, `views.sql`, and `routines.sql`.
