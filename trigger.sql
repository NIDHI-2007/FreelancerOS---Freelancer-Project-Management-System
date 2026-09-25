-- Apply after schema.sql. These triggers protect cross-table rules that a simple
-- foreign key or CHECK constraint cannot express.
USE freelancer_pms;

DROP TRIGGER IF EXISTS trg_contract_requires_accepted_application;
DROP TRIGGER IF EXISTS trg_task_hired_freelancer_insert;
DROP TRIGGER IF EXISTS trg_task_hired_freelancer_update;

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
DELIMITER ;

DELIMITER $$
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
DELIMITER ;

DELIMITER $$
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

DELIMITER ;
