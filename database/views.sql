-- Reporting views for dashboards and DBMS demonstrations.
USE freelancer_pms;

CREATE OR REPLACE VIEW v_contract_payment_summary AS
SELECT c.contract_id,
       c.project_id,
       c.agreed_amount,
       COALESCE(SUM(CASE WHEN p.status = 'completed' THEN p.amount ELSE 0 END), 0) AS completed_amount,
       COALESCE(SUM(CASE WHEN p.status IN ('pending','processing') THEN p.amount ELSE 0 END), 0) AS pending_amount,
       COALESCE(SUM(CASE WHEN p.status = 'refunded' THEN p.amount ELSE 0 END), 0) AS refunded_amount,
       COUNT(p.payment_id) AS payment_count
FROM Contract c
LEFT JOIN Payment p ON p.contract_id = c.contract_id
GROUP BY c.contract_id, c.project_id, c.agreed_amount;

CREATE OR REPLACE VIEW v_user_rating_summary AS
SELECT u.user_id,
       u.full_name,
       u.role,
       COUNT(r.review_id) AS review_count,
       CAST(AVG(r.rating) AS DECIMAL(4,2)) AS average_rating
FROM `User` u
LEFT JOIN Review r ON r.reviewee_id = u.user_id
GROUP BY u.user_id, u.full_name, u.role;

CREATE OR REPLACE VIEW v_freelancer_earnings AS
SELECT f.user_id AS freelancer_id,
       u.full_name,
       COALESCE(SUM(CASE WHEN p.status = 'completed' THEN p.amount ELSE 0 END), 0) AS total_earnings,
       COUNT(CASE WHEN p.status = 'completed' THEN p.payment_id END) AS completed_payment_count
FROM Freelancer f
JOIN `User` u ON u.user_id = f.user_id
LEFT JOIN Payment p ON p.payee_id = f.user_id
GROUP BY f.user_id, u.full_name;

CREATE OR REPLACE VIEW v_client_spending AS
SELECT c.user_id AS client_id,
       u.full_name,
       COALESCE(SUM(CASE WHEN p.status = 'completed' THEN p.amount ELSE 0 END), 0) AS total_spending,
       COUNT(CASE WHEN p.status = 'completed' THEN p.payment_id END) AS completed_payment_count
FROM Client c
JOIN `User` u ON u.user_id = c.user_id
LEFT JOIN Payment p ON p.payer_id = c.user_id
GROUP BY c.user_id, u.full_name;
