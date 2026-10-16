-- Apply after schema.sql. These triggers protect cross-table rules that a simple
-- foreign key or CHECK constraint cannot express.
USE freelancer_pms;

DROP TRIGGER IF EXISTS trg_contract_requires_accepted_application;
DROP TRIGGER IF EXISTS trg_task_hired_freelancer_insert;
DROP TRIGGER IF EXISTS trg_task_hired_freelancer_update;
DROP TRIGGER IF EXISTS trg_payment_contract_parties;
DROP TRIGGER IF EXISTS trg_payment_status_transition;

DELIMITER $$

CREATE TRIGGER trg_contract_requires_accepted_application
BEFORE INSERT ON Contract
FOR EACH ROW
BEGIN
  DECLARE v_application_status VARCHAR(20) DEFAULT NULL;
  DECLARE v_project_status VARCHAR(20) DEFAULT NULL;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_application_status = NULL, v_project_status = NULL;

  SELECT a.status, p.status
    INTO v_application_status, v_project_status
    FROM Application a
    JOIN Project p ON p.project_id = a.project_id
   WHERE a.application_id = NEW.application_id
     AND a.project_id = NEW.project_id;

  IF v_application_status IS NULL OR v_application_status <> 'accepted' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A contract requires an accepted application for the same project';
  END IF;

  IF v_project_status <> 'in_progress' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A contract requires its project to be in progress';
  END IF;
END$$

CREATE TRIGGER trg_task_hired_freelancer_insert
BEFORE INSERT ON Task
FOR EACH ROW
BEGIN
  DECLARE v_freelancer_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_freelancer_id = NULL;

  SELECT a.freelancer_id
    INTO v_freelancer_id
    FROM Contract c
    JOIN Application a ON a.application_id = c.application_id
   WHERE c.contract_id = NEW.contract_id;

  IF v_freelancer_id IS NULL OR NEW.assigned_to <> v_freelancer_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A task must be assigned to the freelancer hired by its contract';
  END IF;
END$$

CREATE TRIGGER trg_task_hired_freelancer_update
BEFORE UPDATE ON Task
FOR EACH ROW
BEGIN
  DECLARE v_freelancer_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_freelancer_id = NULL;

  SELECT a.freelancer_id
    INTO v_freelancer_id
    FROM Contract c
    JOIN Application a ON a.application_id = c.application_id
   WHERE c.contract_id = NEW.contract_id;

  IF v_freelancer_id IS NULL OR NEW.assigned_to <> v_freelancer_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A task must be assigned to the freelancer hired by its contract';
  END IF;
END$$

CREATE TRIGGER trg_payment_contract_parties
BEFORE INSERT ON Payment
FOR EACH ROW
BEGIN
  DECLARE v_client_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE v_freelancer_id BIGINT UNSIGNED DEFAULT NULL;
  DECLARE v_contract_status VARCHAR(20) DEFAULT NULL;
  DECLARE v_milestone_status VARCHAR(20) DEFAULT NULL;
  DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_client_id = NULL, v_freelancer_id = NULL, v_contract_status = NULL, v_milestone_status = NULL;

  SELECT p.client_id, a.freelancer_id, c.status
    INTO v_client_id, v_freelancer_id, v_contract_status
    FROM Contract c
    JOIN Project p ON p.project_id = c.project_id
    JOIN Application a ON a.application_id = c.application_id
   WHERE c.contract_id = NEW.contract_id;

  IF v_client_id IS NULL OR v_contract_status <> 'active' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A payment requires an active contract';
  END IF;
  IF NEW.payer_id <> v_client_id OR NEW.payee_id <> v_freelancer_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment parties must match the contract participants';
  END IF;
  IF NEW.status <> 'pending' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A new payment must start as pending';
  END IF;
  IF NEW.milestone_id IS NOT NULL THEN
    SELECT status INTO v_milestone_status
      FROM Milestone
     WHERE milestone_id = NEW.milestone_id AND contract_id = NEW.contract_id;
    IF v_milestone_status IS NULL OR v_milestone_status <> 'approved' THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A milestone payment requires an approved milestone on the same contract';
    END IF;
  END IF;
END$$

CREATE TRIGGER trg_payment_status_transition
BEFORE UPDATE ON Payment
FOR EACH ROW
BEGIN
  IF NEW.contract_id <> OLD.contract_id
     OR NOT (NEW.milestone_id <=> OLD.milestone_id)
     OR NEW.payer_id <> OLD.payer_id
     OR NEW.payee_id <> OLD.payee_id
     OR NEW.amount <> OLD.amount THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payment ownership and amount cannot be changed';
  END IF;

  IF NOT (
       NEW.status = OLD.status
       OR (OLD.status = 'pending' AND NEW.status IN ('processing','completed','failed'))
       OR (OLD.status = 'processing' AND NEW.status IN ('completed','failed'))
       OR (OLD.status = 'completed' AND NEW.status = 'refunded')
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid payment status transition';
  END IF;
  IF NEW.status = 'completed'
     AND (NEW.transaction_reference IS NULL OR CHAR_LENGTH(TRIM(NEW.transaction_reference)) = 0) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Completed payments require a transaction reference';
  END IF;
END$$

DELIMITER ;
