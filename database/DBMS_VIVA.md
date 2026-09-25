# DBMS Viva Questions and Answers

1. **Why are skills stored in separate tables?**  
   A freelancer or project can have multiple skills, and a skill can belong to many freelancers/projects. `Freelancer_Skill` and `Project_Skill` model these M:N relations without comma-separated values.

2. **How does this schema satisfy 1NF?**  
   Each column stores one value; multi-valued skills are moved to bridge rows.

3. **How do the bridge tables satisfy 2NF?**  
   Their non-key facts depend on the full composite key. For example, proficiency depends on `(freelancer_id, skill_id)`.

4. **Is every table strictly in 3NF?**  
   The entity and bridge core is. Event data retains controlled redundancy in task assignment, payment parties, and message receiver; `DBMS_REVIEW.md` explains these fields and the trade-off.

5. **How is a client profile linked to an account?**  
   `Client.user_id` is both its primary key and a foreign key to `User.user_id`, making the relationship 1:1.

6. **How is duplicate bidding prevented?**  
   `Application` has `UNIQUE(project_id, freelancer_id)`, so one freelancer cannot submit multiple bids for the same project.

7. **How are invalid states and amounts rejected?**  
   `CHECK` constraints restrict status values and ensure values such as bids, rates, ratings, and budgets are within allowed ranges. `NOT NULL` and defaults cover required and initial values.

8. **How does the schema enforce a contract's application/project consistency?**  
   A composite FK from `(Contract.application_id, Contract.project_id)` references the corresponding pair in `Application`.

9. **Where are transactions important?**  
   Accepting an application changes application/project state and creates a contract atomically. Payment and milestone lifecycle changes also use transaction boundaries so partial updates can roll back.

10. **What do the triggers enforce?**  
    They check cross-table conditions for contract creation from accepted applications and ensure assigned tasks belong to the hired freelancer.

11. **What information do the views summarize?**  
    Views expose payment totals, freelancer earnings, client spending, and user ratings for dashboards and reports.

12. **Why use indexes?**  
    Indexes support frequent filters and joins such as project status/category, user ownership, application state, unread items, and payment settlement by milestone/status. They trade storage and write cost for faster lookup.

13. **How does the project demonstrate `HAVING`?**  
    Project matching groups required skills and filters groups whose matched skill count equals the project's required skill count.

14. **What is the verification limitation?**  
    API tests use SQLite as a test double; MySQL-specific constraints, triggers, routines, and execution plans need a MySQL 8.0.16+ run.
