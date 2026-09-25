CREATE DATABASE IF NOT EXISTS freelancer_pms;
-- Freelancer Project Management System
-- Target: MySQL 8.0.16+ (CHECK constraints are enforced from 8.0.16).
CREATE DATABASE IF NOT EXISTS freelancer_pms
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE freelancer_pms;

CREATE TABLE IF NOT EXISTS `User` (
  user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(254) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(150) NOT NULL,
  role VARCHAR(20) NOT NULL,
  account_status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  UNIQUE KEY uq_user_email (email),
  CONSTRAINT chk_user_role CHECK (role IN ('client','freelancer','admin')),
  CONSTRAINT chk_user_status CHECK (account_status IN ('active','suspended','closed'))
) ENGINE=InnoDB;

-- Persistent JWT logout revocation, shared by workers and retained across restarts.
CREATE TABLE IF NOT EXISTS Revoked_Token (
  token_jti CHAR(36) NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (token_jti),
  KEY ix_revoked_token_expiry (expires_at)
) ENGINE=InnoDB;

-- Reset tokens are random values emailed to the user; only their SHA-256 digests are stored.
CREATE TABLE IF NOT EXISTS Password_Reset_Token (
  reset_token_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  token_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (reset_token_id),
  UNIQUE KEY uq_password_reset_token_hash (token_hash),
  KEY ix_password_reset_user_expiry (user_id, expires_at),
  CONSTRAINT fk_password_reset_user FOREIGN KEY (user_id) REFERENCES `User` (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Client (
  user_id BIGINT UNSIGNED NOT NULL,
  company_name VARCHAR(160) NULL,
  bio TEXT NULL,
  location VARCHAR(120) NULL,
  website VARCHAR(255) NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_client_user FOREIGN KEY (user_id) REFERENCES `User` (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Freelancer (
  user_id BIGINT UNSIGNED NOT NULL,
  headline VARCHAR(180) NULL,
  bio TEXT NULL,
  hourly_rate DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  experience_years SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  location VARCHAR(120) NULL,
  availability_status VARCHAR(20) NOT NULL DEFAULT 'available',
  PRIMARY KEY (user_id),
  CONSTRAINT chk_freelancer_rate CHECK (hourly_rate >= 0),
  CONSTRAINT chk_freelancer_experience CHECK (experience_years >= 0),
  CONSTRAINT chk_freelancer_availability CHECK (availability_status IN ('available','busy','unavailable')),
  CONSTRAINT fk_freelancer_user FOREIGN KEY (user_id) REFERENCES `User` (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Skill (
  skill_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  PRIMARY KEY (skill_id),
  UNIQUE KEY uq_skill_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Freelancer_Skill (
  freelancer_id BIGINT UNSIGNED NOT NULL,
  skill_id BIGINT UNSIGNED NOT NULL,
  proficiency_level TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (freelancer_id, skill_id),
  CONSTRAINT chk_freelancer_skill_level CHECK (proficiency_level BETWEEN 1 AND 5),
  CONSTRAINT fk_fs_freelancer FOREIGN KEY (freelancer_id) REFERENCES Freelancer (user_id) ON DELETE CASCADE,
  CONSTRAINT fk_fs_skill FOREIGN KEY (skill_id) REFERENCES Skill (skill_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Portfolio (
  portfolio_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  freelancer_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(180) NOT NULL,
  description TEXT NULL,
  project_url VARCHAR(2048) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (portfolio_id),
  KEY ix_portfolio_freelancer (freelancer_id),
  CONSTRAINT fk_portfolio_freelancer FOREIGN KEY (freelancer_id) REFERENCES Freelancer (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Category (
  category_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(500) NULL,
  PRIMARY KEY (category_id),
  UNIQUE KEY uq_category_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Project (
  project_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  client_id BIGINT UNSIGNED NOT NULL,
  category_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(180) NOT NULL,
  description TEXT NOT NULL,
  budget_min DECIMAL(12,2) NOT NULL,
  budget_max DECIMAL(12,2) NOT NULL,
  deadline DATE NULL,
  project_type VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'open',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (project_id),
  KEY ix_project_client (client_id),
  KEY ix_project_category_status_deadline (category_id, status, deadline),
  KEY ix_project_status_created (status, created_at),
  CONSTRAINT chk_project_budget CHECK (budget_min >= 0 AND budget_max >= budget_min),
  CONSTRAINT chk_project_type CHECK (project_type IN ('fixed','hourly')),
  CONSTRAINT chk_project_status CHECK (status IN ('draft','open','in_progress','completed','cancelled')),
  CONSTRAINT fk_project_client FOREIGN KEY (client_id) REFERENCES Client (user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_project_category FOREIGN KEY (category_id) REFERENCES Category (category_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Project_Skill (
  project_id BIGINT UNSIGNED NOT NULL,
  skill_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (project_id, skill_id),
  KEY ix_project_skill_skill (skill_id),
  CONSTRAINT fk_ps_project FOREIGN KEY (project_id) REFERENCES Project (project_id) ON DELETE CASCADE,
  CONSTRAINT fk_ps_skill FOREIGN KEY (skill_id) REFERENCES Skill (skill_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Application (
  application_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  freelancer_id BIGINT UNSIGNED NOT NULL,
  proposal TEXT NOT NULL,
  bid_amount DECIMAL(12,2) NOT NULL,
  estimated_days SMALLINT UNSIGNED NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (application_id),
  UNIQUE KEY uq_application_project_freelancer (project_id, freelancer_id),
  UNIQUE KEY uq_application_id_project (application_id, project_id),
  KEY ix_application_freelancer_status (freelancer_id, status),
  KEY ix_application_project_status (project_id, status),
  CONSTRAINT chk_application_bid CHECK (bid_amount > 0),
  CONSTRAINT chk_application_days CHECK (estimated_days > 0),
  CONSTRAINT chk_application_status CHECK (status IN ('pending','shortlisted','accepted','rejected','withdrawn')),
  CONSTRAINT fk_application_project FOREIGN KEY (project_id) REFERENCES Project (project_id) ON DELETE CASCADE,
  CONSTRAINT fk_application_freelancer FOREIGN KEY (freelancer_id) REFERENCES Freelancer (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Contract (
  contract_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  application_id BIGINT UNSIGNED NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NULL,
  agreed_amount DECIMAL(12,2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (contract_id),
  UNIQUE KEY uq_contract_project (project_id),
  UNIQUE KEY uq_contract_application (application_id),
  CONSTRAINT chk_contract_amount CHECK (agreed_amount > 0),
  CONSTRAINT chk_contract_dates CHECK (end_date IS NULL OR end_date >= start_date),
  CONSTRAINT chk_contract_status CHECK (status IN ('active','completed','cancelled','disputed')),
  CONSTRAINT fk_contract_project FOREIGN KEY (project_id) REFERENCES Project (project_id) ON DELETE RESTRICT,
  CONSTRAINT fk_contract_application_project FOREIGN KEY (application_id, project_id)
    REFERENCES Application (application_id, project_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Task (
  task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contract_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(180) NOT NULL,
  description TEXT NULL,
  assigned_to BIGINT UNSIGNED NOT NULL,
  due_date DATE NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'todo',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (task_id),
  KEY ix_task_contract_status (contract_id, status),
  KEY ix_task_assignee_status (assigned_to, status),
  CONSTRAINT chk_task_status CHECK (status IN ('todo','in_progress','submitted','completed','cancelled')),
  CONSTRAINT fk_task_contract FOREIGN KEY (contract_id) REFERENCES Contract (contract_id) ON DELETE CASCADE,
  CONSTRAINT fk_task_freelancer FOREIGN KEY (assigned_to) REFERENCES Freelancer (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Milestone (
  milestone_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contract_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(180) NOT NULL,
  description TEXT NULL,
  amount DECIMAL(12,2) NOT NULL,
  due_date DATE NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  submitted_at DATETIME NULL,
  reviewed_at DATETIME NULL,
  PRIMARY KEY (milestone_id),
  UNIQUE KEY uq_milestone_contract_title (contract_id, title),
  UNIQUE KEY uq_milestone_contract_id (contract_id, milestone_id),
  KEY ix_milestone_contract_status (contract_id, status),
  CONSTRAINT chk_milestone_amount CHECK (amount > 0),
  CONSTRAINT chk_milestone_status CHECK (status IN ('pending','submitted','approved','rejected','paid')),
  CONSTRAINT fk_milestone_contract FOREIGN KEY (contract_id) REFERENCES Contract (contract_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Payment (
  payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contract_id BIGINT UNSIGNED NOT NULL,
  milestone_id BIGINT UNSIGNED NULL,
  payer_id BIGINT UNSIGNED NOT NULL,
  payee_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  payment_method VARCHAR(40) NULL,
  transaction_reference VARCHAR(120) NULL,
  paid_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (payment_id),
  UNIQUE KEY uq_payment_transaction_reference (transaction_reference),
  KEY ix_payment_contract_status (contract_id, status),
  KEY ix_payment_milestone_status (milestone_id, status),
  KEY ix_payment_payer_created (payer_id, created_at),
  KEY ix_payment_payee_created (payee_id, created_at),
  CONSTRAINT chk_payment_amount CHECK (amount > 0),
  CONSTRAINT chk_payment_status CHECK (status IN ('pending','processing','completed','failed','refunded')),
  CONSTRAINT chk_payment_distinct_parties CHECK (payer_id <> payee_id),
  CONSTRAINT fk_payment_contract FOREIGN KEY (contract_id) REFERENCES Contract (contract_id) ON DELETE RESTRICT,
  CONSTRAINT fk_payment_contract_milestone FOREIGN KEY (contract_id, milestone_id)
    REFERENCES Milestone (contract_id, milestone_id) ON DELETE RESTRICT,
  CONSTRAINT fk_payment_payer FOREIGN KEY (payer_id) REFERENCES `User` (user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_payment_payee FOREIGN KEY (payee_id) REFERENCES `User` (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Review (
  review_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contract_id BIGINT UNSIGNED NOT NULL,
  reviewer_id BIGINT UNSIGNED NOT NULL,
  reviewee_id BIGINT UNSIGNED NOT NULL,
  rating TINYINT UNSIGNED NOT NULL,
  comment TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (review_id),
  UNIQUE KEY uq_review_contract_reviewer (contract_id, reviewer_id),
  KEY ix_review_reviewee (reviewee_id),
  CONSTRAINT chk_review_rating CHECK (rating BETWEEN 1 AND 5),
  CONSTRAINT chk_review_distinct_users CHECK (reviewer_id <> reviewee_id),
  CONSTRAINT fk_review_contract FOREIGN KEY (contract_id) REFERENCES Contract (contract_id) ON DELETE RESTRICT,
  CONSTRAINT fk_review_reviewer FOREIGN KEY (reviewer_id) REFERENCES `User` (user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_review_reviewee FOREIGN KEY (reviewee_id) REFERENCES `User` (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Message (
  message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contract_id BIGINT UNSIGNED NOT NULL,
  sender_id BIGINT UNSIGNED NOT NULL,
  receiver_id BIGINT UNSIGNED NOT NULL,
  body TEXT NOT NULL,
  sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  read_at DATETIME NULL,
  PRIMARY KEY (message_id),
  KEY ix_message_contract_sent (contract_id, sent_at),
  KEY ix_message_receiver_read (receiver_id, read_at),
  CONSTRAINT chk_message_distinct_users CHECK (sender_id <> receiver_id),
  CONSTRAINT fk_message_contract FOREIGN KEY (contract_id) REFERENCES Contract (contract_id) ON DELETE CASCADE,
  CONSTRAINT fk_message_sender FOREIGN KEY (sender_id) REFERENCES `User` (user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_message_receiver FOREIGN KEY (receiver_id) REFERENCES `User` (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Notification (
  notification_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  message VARCHAR(1000) NOT NULL,
  notification_type VARCHAR(40) NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (notification_id),
  KEY ix_notification_user_read_created (user_id, is_read, created_at),
  CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES `User` (user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Dispute (
  dispute_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contract_id BIGINT UNSIGNED NOT NULL,
  opened_by BIGINT UNSIGNED NOT NULL,
  reason VARCHAR(180) NOT NULL,
  description TEXT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'open',
  admin_id BIGINT UNSIGNED NULL,
  resolution TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME NULL,
  PRIMARY KEY (dispute_id),
  KEY ix_dispute_status_created (status, created_at),
  KEY ix_dispute_contract (contract_id),
  CONSTRAINT chk_dispute_status CHECK (status IN ('open','investigating','resolved','closed')),
  CONSTRAINT fk_dispute_contract FOREIGN KEY (contract_id) REFERENCES Contract (contract_id) ON DELETE RESTRICT,
  CONSTRAINT fk_dispute_opener FOREIGN KEY (opened_by) REFERENCES `User` (user_id) ON DELETE RESTRICT,
  CONSTRAINT fk_dispute_admin FOREIGN KEY (admin_id) REFERENCES `User` (user_id) ON DELETE RESTRICT
) ENGINE=InnoDB;
