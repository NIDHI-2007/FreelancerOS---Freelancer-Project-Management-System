-- Stored functions and procedures for repeatable database operations.
-- sp_accept_application_and_create_contract and sp_settle_approved_milestone_payment
-- manage their own transaction and should be called as standalone operations.
USE freelancer_pms;

DROP FUNCTION IF EXISTS fn_user_average_rating;
DROP FUNCTION IF EXISTS fn_contract_remaining_balance;
DROP PROCEDURE IF EXISTS sp_accept_application_and_create_contract;
DROP PROCEDURE IF EXISTS sp_settle_approved_milestone_payment;

DELIMITER $$

CREATE FUNCTION fn_user_average_rating(p_user_id BIGINT UNSIGNED)
RETURNS DECIMAL(4,2)
READS SQL DATA
BEGIN
  DECLARE v_average DECIMAL(4,2) DEFAULT NULL;
  SELECT CAST(AVG(rating) AS DECIMAL(4,2))
    INTO v_average
    FROM Review
   WHERE reviewee_id = p_user_id;
  RETURN v_average;
END$$

CREATE FUNCTION fn_contract_remaining_balance(p_contract_id BIGINT UNSIGNED)
RETURNS DECIMAL(12,2)
READS SQL DATA
BEGIN
  DECLARE v_balance DECIMAL(12,2) DEFAULT NULL;
  SELECT GREATEST(c.agreed_amount - COALESCE(SUM(CASE WHEN p.status = 'completed' THEN p.amount ELSE 0 END), 0), 0)
    INTO v_balance
    FROM Contract c
    LEFT JOIN Payment p ON p.contract_id = c.contract_id
   WHERE c.contract_id = p_contract_id
   GROUP BY c.contract_id, c.agreed_amount;
  RETURN v_balance;
END$$

CREATE PROCEDURE sp_accept_application_and_create_contract(
  IN p_application_id BIGINT UNSIGNED,
  IN p_agreed_amount DECIMAL(12,2),
  OUT p_contract_id BIGINT UNSIGNED
)
BEGIN
  DECLARE v_project_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE v_bid_amount DECIMAL(12,2) DEFAULT NULL;
  DECLARE v_application_status VARCHAR(20) DEFAULT NULL;
  DECLARE v_project_status VARCHAR(20) DEFAULT NULL;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_application_status = NULL, v_project_status = NULL;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  SET p_contract_id = NULL;
  START TRANSACTION;
  SELECT a.project_id, a.bid_amount, a.status, p.status
    INTO v_project_id, v_bid_amount, v_application_status, v_project_status
    FROM Application a JOIN Project p ON p.project_id = a.project_id
   WHERE a.application_id = p_application_id
   FOR UPDATE;

  IF v_application_status IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application was not found';
  END IF;
  IF v_application_status NOT IN ('pending','shortlisted') OR v_project_status <> 'open' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Application or project is not available for hiring';
  END IF;
  IF p_agreed_amount IS NOT NULL AND p_agreed_amount <= 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Agreed amount must be positive';
  END IF;

  UPDATE Application SET status = 'accepted' WHERE application_id = p_application_id;
  UPDATE Project SET status = 'in_progress' WHERE project_id = v_project_id;
  INSERT INTO Contract (project_id, application_id, start_date, agreed_amount)
  VALUES (v_project_id, p_application_id, CURRENT_DATE(), COALESCE(p_agreed_amount, v_bid_amount));
  SET p_contract_id = LAST_INSERT_ID();
  COMMIT;
END$$

CREATE PROCEDURE sp_settle_approved_milestone_payment(
  IN p_payment_id BIGINT UNSIGNED,
  IN p_transaction_reference VARCHAR(120)
)
BEGIN
  DECLARE v_contract_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE v_milestone_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE v_payment_status VARCHAR(20) DEFAULT NULL;
  DECLARE v_milestone_status VARCHAR(20) DEFAULT NULL;
  DECLARE v_milestone_amount DECIMAL(12,2) DEFAULT NULL;
  DECLARE v_paid_amount DECIMAL(12,2) DEFAULT 0;
  DECLARE v_found TINYINT DEFAULT 1;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_found = 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;
  SELECT contract_id, milestone_id, status
    INTO v_contract_id, v_milestone_id, v_payment_status
    FROM Payment WHERE payment_id = p_payment_id FOR UPDATE;
  IF v_found = 0 OR v_milestone_id IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Milestone payment was not found';
  END IF;
  IF v_payment_status NOT IN ('pending','processing') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment is not awaiting settlement';
  END IF;
  IF p_transaction_reference IS NULL OR CHAR_LENGTH(TRIM(p_transaction_reference)) = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Transaction reference is required';
  END IF;

  SET v_found = 1;
  SELECT status, amount
    INTO v_milestone_status, v_milestone_amount
    FROM Milestone WHERE milestone_id = v_milestone_id AND contract_id = v_contract_id FOR UPDATE;
  IF v_found = 0 OR v_milestone_status <> 'approved' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Milestone must be approved before settlement';
  END IF;

  UPDATE Payment
     SET status = 'completed', transaction_reference = TRIM(p_transaction_reference), paid_at = CURRENT_TIMESTAMP
   WHERE payment_id = p_payment_id;
  SELECT COALESCE(SUM(amount), 0) INTO v_paid_amount
    FROM Payment WHERE milestone_id = v_milestone_id AND status = 'completed';
  IF v_paid_amount > v_milestone_amount THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Settled payments exceed the milestone amount';
  END IF;
  IF v_paid_amount = v_milestone_amount THEN
    UPDATE Milestone SET status = 'paid' WHERE milestone_id = v_milestone_id;
  END IF;
  COMMIT;
END$$

DELIMITER ;
