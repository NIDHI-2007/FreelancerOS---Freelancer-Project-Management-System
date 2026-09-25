-- Read-focused DBMS viva/demo queries. Uses the deterministic seed IDs by default.
USE freelancer_pms;

-- 1. JOIN: open projects with their client and category.
SELECT p.project_id, p.title, u.full_name AS client, c.name AS category,
       p.budget_min, p.budget_max, p.deadline, p.project_type, p.status
FROM Project p
JOIN Client cl ON cl.user_id = p.client_id
JOIN `User` u ON u.user_id = cl.user_id
JOIN Category c ON c.category_id = p.category_id
WHERE p.status = 'open'
ORDER BY p.created_at DESC;

-- 2. GROUP BY / aggregate / HAVING: projects with at least one application.
SELECT p.project_id, p.title, COUNT(a.application_id) AS application_count,
       MIN(a.bid_amount) AS lowest_bid, MAX(a.bid_amount) AS highest_bid,
       AVG(a.bid_amount) AS average_bid
FROM Project p
LEFT JOIN Application a ON a.project_id = p.project_id
GROUP BY p.project_id, p.title
HAVING COUNT(a.application_id) > 0
ORDER BY application_count DESC;

-- 3. M:N skill matching: freelancers possessing every skill required by a project.
SET @demo_project_id = 2;
SELECT f.user_id AS freelancer_id, u.full_name,
       COUNT(DISTINCT ps.skill_id) AS matched_skill_count
FROM Project_Skill ps
JOIN Freelancer_Skill fs ON fs.skill_id = ps.skill_id
JOIN Freelancer f ON f.user_id = fs.freelancer_id
JOIN `User` u ON u.user_id = f.user_id
WHERE ps.project_id = @demo_project_id
GROUP BY f.user_id, u.full_name
HAVING COUNT(DISTINCT ps.skill_id) = (
  SELECT COUNT(*) FROM Project_Skill WHERE project_id = @demo_project_id
);

-- 4. Subquery: projects whose maximum budget is above the platform average.
SELECT project_id, title, budget_max
FROM Project
WHERE budget_max > (SELECT AVG(budget_max) FROM Project)
ORDER BY budget_max DESC;

-- 5. Reporting views: payment reconciliation, freelancer earnings, client spending, ratings.
SELECT * FROM v_contract_payment_summary ORDER BY contract_id;
SELECT * FROM v_freelancer_earnings ORDER BY total_earnings DESC;
SELECT * FROM v_client_spending ORDER BY total_spending DESC;
SELECT * FROM v_user_rating_summary ORDER BY average_rating DESC, review_count DESC;

-- 6. Stored functions.
SELECT fn_user_average_rating(2) AS freelancer_average_rating;
SELECT fn_contract_remaining_balance(1) AS contract_remaining_balance;

-- 7. Read-only transaction demonstration: acquire a row lock, inspect, then roll back.
START TRANSACTION;
SELECT contract_id, status, agreed_amount
FROM Contract
WHERE contract_id = 1
FOR UPDATE;
ROLLBACK;

-- 8. Inspect trigger and index definitions.
SHOW TRIGGERS;
SHOW INDEX FROM Payment;

-- These procedures commit changes. Run only against deliberate demo records:
-- CALL sp_accept_application_and_create_contract(<pending_application_id>, NULL, @new_contract_id);
-- SELECT @new_contract_id;
-- CALL sp_settle_approved_milestone_payment(<pending_milestone_payment_id>, 'VIVA-REFERENCE-001');
