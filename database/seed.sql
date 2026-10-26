-- Deterministic local/college demonstration data for freelancer_pms.
-- Demo login password for all six accounts: Demo@123 (Werkzeug scrypt hashes below).
-- This seed is rerunnable: it replaces only the named demo projects and their
-- dependent workflow rows, plus the portfolio/skill links for these demo users.
-- Do not use this demo dataset as production data.
USE freelancer_pms;

START TRANSACTION;

-- Demo identities (emails use the existing example.test fixture convention).
INSERT INTO `User` (email, password_hash, full_name, role, account_status, created_at) VALUES
  ('client@example.test', 'scrypt:32768:8:1$JpAD0hcgi5GlVDqX$8970cdb821ee4619486abbdeacd55091e2b059f6dd1a3fcdf6f1f7bc1a3b000acb7080f1fc3f582aaeead4ad1580bb02468c094f5c38aa7b8ec9ef7f4699a7d6', 'Avery Client', 'client', 'active', '2026-09-01 09:00:00'),
  ('client2@example.test', 'scrypt:32768:8:1$8JEtQcP9tyk1LqcL$570839c5ccc3f0b6a8342a6aa69d87bcc087904499f50a268fc096228712dc078008c90aaf74eb6c3b87203e1ead13415ea003b76ee0f5be7427b96a724c135f', 'Morgan Client', 'client', 'active', '2026-09-02 09:00:00'),
  ('freelancer@example.test', 'scrypt:32768:8:1$3n73g28jVOlfaRAr$2f05f4fc6fd9d536947f8a2f7de4c42102e2ec1815c9591f274610ba45f2a3376aab15e12e0330de30627e155ab3d3c25698ce084a1c8d200dd07d438d024bbd', 'Jordan Freelancer', 'freelancer', 'active', '2026-09-03 09:00:00'),
  ('freelancer2@example.test', 'scrypt:32768:8:1$TIaeh5arFwyJgLKI$8f13e9eacf5cc67a52ae54b0dc78c5c9a2d033d6bab3fce6b6e5708fe79a984330e77f3b84d2088b4805d77fbf23c32c5a1aa2e16519b85cab72116449c5a707', 'Taylor Designer', 'freelancer', 'active', '2026-09-04 09:00:00'),
  ('freelancer3@example.test', 'scrypt:32768:8:1$ZHjbfONmoCURi6BD$2d387912efd36331111362e2a308e7318e99220e744bec9dc6a39d5a16b31c5c4b5aca6159a7fcc0a34ee9286eb71d723ef7bd203c50221c449998d666e775e8', 'Casey Marketer', 'freelancer', 'active', '2026-09-05 09:00:00'),
  ('admin@example.test', 'scrypt:32768:8:1$AL3EK9PPJ8gTXOAI$1f5695129ec1c77514ad83aba481cad4129e36e916df15a13afafe054287e1500d0233639155e842885a15471d2fcf662e9c380f6323bbf82f1ed3f06d0b0c0e', 'Riley Admin', 'admin', 'active', '2026-09-06 09:00:00')
ON DUPLICATE KEY UPDATE
  password_hash = VALUES(password_hash),
  full_name = VALUES(full_name),
  role = VALUES(role),
  account_status = 'active',
  created_at = VALUES(created_at);

SET @client_a = (SELECT user_id FROM `User` WHERE email = 'client@example.test');
SET @client_b = (SELECT user_id FROM `User` WHERE email = 'client2@example.test');
SET @freelancer_a = (SELECT user_id FROM `User` WHERE email = 'freelancer@example.test');
SET @freelancer_b = (SELECT user_id FROM `User` WHERE email = 'freelancer2@example.test');
SET @freelancer_c = (SELECT user_id FROM `User` WHERE email = 'freelancer3@example.test');
SET @admin = (SELECT user_id FROM `User` WHERE email = 'admin@example.test');

-- Remove only prior demo workflows belonging to the exact demo clients and
-- named fixture projects (including the older seed's three project names).
DELETE d FROM Dispute d JOIN Contract c ON c.contract_id = d.contract_id
JOIN Project p ON p.project_id = c.project_id
WHERE p.client_id IN (@client_a, @client_b)
  AND p.title IN (
    'Build a project tracker', 'Design a landing page', 'Design a product launch kit',
    'FreelanceOS Demo - Analytics dashboard refresh',
    'FreelanceOS Demo - Product launch design system',
    'FreelanceOS Demo - Mobile onboarding experience',
    'FreelanceOS Demo - Organic search campaign',
    'FreelanceOS Demo - Customer support portal'
  );
DELETE FROM Review WHERE contract_id IN (
  SELECT c.contract_id FROM Contract c JOIN Project p ON p.project_id = c.project_id
  WHERE p.client_id IN (@client_a, @client_b)
    AND p.title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE FROM Payment WHERE contract_id IN (
  SELECT c.contract_id FROM Contract c JOIN Project p ON p.project_id = c.project_id
  WHERE p.client_id IN (@client_a, @client_b)
    AND p.title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE FROM Message WHERE contract_id IN (
  SELECT c.contract_id FROM Contract c JOIN Project p ON p.project_id = c.project_id
  WHERE p.client_id IN (@client_a, @client_b)
    AND p.title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE FROM Task WHERE contract_id IN (
  SELECT c.contract_id FROM Contract c JOIN Project p ON p.project_id = c.project_id
  WHERE p.client_id IN (@client_a, @client_b)
    AND p.title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE FROM Milestone WHERE contract_id IN (
  SELECT c.contract_id FROM Contract c JOIN Project p ON p.project_id = c.project_id
  WHERE p.client_id IN (@client_a, @client_b)
    AND p.title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE c FROM Contract c JOIN Project p ON p.project_id = c.project_id
WHERE p.client_id IN (@client_a, @client_b)
  AND p.title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
    'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
    'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
    'FreelanceOS Demo - Customer support portal');
DELETE FROM Application WHERE project_id IN (
  SELECT project_id FROM Project WHERE client_id IN (@client_a, @client_b)
    AND title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE FROM Project_Skill WHERE project_id IN (
  SELECT project_id FROM Project WHERE client_id IN (@client_a, @client_b)
    AND title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
      'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
      'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
      'FreelanceOS Demo - Customer support portal')
);
DELETE FROM Project WHERE client_id IN (@client_a, @client_b)
  AND title IN ('Build a project tracker', 'Design a landing page', 'Design a product launch kit',
    'FreelanceOS Demo - Analytics dashboard refresh', 'FreelanceOS Demo - Product launch design system',
    'FreelanceOS Demo - Mobile onboarding experience', 'FreelanceOS Demo - Organic search campaign',
    'FreelanceOS Demo - Customer support portal');

DELETE FROM Portfolio WHERE freelancer_id IN (@freelancer_a, @freelancer_b, @freelancer_c)
  AND title IN ('Inventory dashboard', 'Mobile banking concept', 'FreelanceOS Demo - Marketplace analytics',
    'FreelanceOS Demo - Wellness app redesign', 'FreelanceOS Demo - SEO content hub');
DELETE FROM Freelancer_Skill WHERE freelancer_id IN (@freelancer_a, @freelancer_b, @freelancer_c);
DELETE FROM Notification WHERE user_id IN (@client_a, @client_b, @freelancer_a, @freelancer_b, @freelancer_c, @admin)
  AND message IN (
    'A milestone was submitted for review.', 'Your application was accepted.',
    'FreelanceOS demo: your application was accepted.',
    'FreelanceOS demo: a milestone is ready for review.',
    'FreelanceOS demo: milestone payment completed.',
    'FreelanceOS demo: a new message is waiting.',
    'FreelanceOS demo: your contract is complete.',
    'A client has shortlisted your mobile onboarding proposal.'
  );

INSERT INTO Client (user_id, company_name, bio, location, website) VALUES
  (@client_a, 'Northstar Digital Studio', 'A small product team building accessible services for local businesses.', 'Toronto, Canada', 'https://northstar.example.test'),
  (@client_b, 'Juniper Works', 'An early-stage team focused on useful education and wellness products.', 'Vancouver, Canada', 'https://juniper.example.test')
ON DUPLICATE KEY UPDATE company_name = VALUES(company_name), bio = VALUES(bio), location = VALUES(location), website = VALUES(website);

INSERT INTO Freelancer (user_id, headline, bio, hourly_rate, experience_years, location, availability_status) VALUES
  (@freelancer_a, 'Full-stack web developer', 'Builds reliable Flask and MySQL services with clear, accessible interfaces.', 62.00, 6, 'Toronto, Canada', 'busy'),
  (@freelancer_b, 'Product and UI/UX designer', 'Turns research and product goals into practical, polished web and mobile experiences.', 54.00, 5, 'Montreal, Canada', 'available'),
  (@freelancer_c, 'Digital marketing specialist', 'Plans search-focused content and measures organic growth for small teams.', 42.00, 4, 'Calgary, Canada', 'available')
ON DUPLICATE KEY UPDATE headline = VALUES(headline), bio = VALUES(bio), hourly_rate = VALUES(hourly_rate),
  experience_years = VALUES(experience_years), location = VALUES(location), availability_status = VALUES(availability_status);

INSERT INTO Skill (name) VALUES
  ('Python'), ('Flask'), ('MySQL'), ('JavaScript'), ('React'), ('HTML/CSS'),
  ('Figma'), ('UI/UX'), ('Machine Learning'), ('Data Analysis'), ('SEO'), ('Content Writing')
ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO Category (name, description) VALUES
  ('Web Development', 'Websites, web applications, and backend services'),
  ('Mobile Development', 'Mobile app design and implementation'),
  ('Design', 'Product design, user experience, and visual systems'),
  ('Data Science', 'Analytics, reporting, and machine learning projects'),
  ('Digital Marketing', 'Search, content, and online growth projects')
ON DUPLICATE KEY UPDATE description = VALUES(description);

INSERT INTO Freelancer_Skill (freelancer_id, skill_id, proficiency_level)
SELECT @freelancer_a, skill_id, CASE name WHEN 'Python' THEN 5 WHEN 'Flask' THEN 5 WHEN 'MySQL' THEN 4 WHEN 'JavaScript' THEN 4 WHEN 'HTML/CSS' THEN 4 ELSE 3 END
FROM Skill WHERE name IN ('Python', 'Flask', 'MySQL', 'JavaScript', 'HTML/CSS');
INSERT INTO Freelancer_Skill (freelancer_id, skill_id, proficiency_level)
SELECT @freelancer_b, skill_id, CASE name WHEN 'Figma' THEN 5 WHEN 'UI/UX' THEN 5 WHEN 'HTML/CSS' THEN 3 ELSE 3 END
FROM Skill WHERE name IN ('Figma', 'UI/UX', 'HTML/CSS');
INSERT INTO Freelancer_Skill (freelancer_id, skill_id, proficiency_level)
SELECT @freelancer_c, skill_id, CASE name WHEN 'SEO' THEN 5 WHEN 'Content Writing' THEN 4 WHEN 'Data Analysis' THEN 3 ELSE 3 END
FROM Skill WHERE name IN ('SEO', 'Content Writing', 'Data Analysis');

INSERT INTO Portfolio (freelancer_id, title, description, project_url, created_at) VALUES
  (@freelancer_a, 'FreelanceOS Demo - Marketplace analytics', 'A responsive analytics dashboard with searchable project and payment summaries.', 'https://example.test/portfolio/marketplace-analytics', '2026-08-14 10:00:00'),
  (@freelancer_b, 'FreelanceOS Demo - Wellness app redesign', 'A mobile-first wellness product concept with a reusable component library.', 'https://example.test/portfolio/wellness-app', '2026-07-21 10:00:00'),
  (@freelancer_c, 'FreelanceOS Demo - SEO content hub', 'A content structure and keyword plan for a growing online learning service.', 'https://example.test/portfolio/content-hub', '2026-06-09 10:00:00');

INSERT INTO Project (client_id, category_id, title, description, budget_min, budget_max, deadline, project_type, status, created_at, updated_at) VALUES
  (@client_a, (SELECT category_id FROM Category WHERE name = 'Web Development'), 'FreelanceOS Demo - Analytics dashboard refresh', 'Improve a business analytics workspace with accessible charts, saved filters, and a maintainable Flask API.', 4800.00, 6200.00, '2026-12-18', 'fixed', 'in_progress', '2026-09-20 09:00:00', '2026-09-20 09:00:00'),
  (@client_b, (SELECT category_id FROM Category WHERE name = 'Design'), 'FreelanceOS Demo - Product launch design system', 'Deliver a compact visual system, responsive landing page, and handoff notes for a new wellness product.', 3200.00, 4200.00, '2026-09-30', 'fixed', 'in_progress', '2026-07-20 09:00:00', '2026-07-20 09:00:00'),
  (@client_a, (SELECT category_id FROM Category WHERE name = 'Mobile Development'), 'FreelanceOS Demo - Mobile onboarding experience', 'Design and implement a clear onboarding flow with account setup, progress feedback, and responsive screens.', 1800.00, 2800.00, '2027-01-22', 'fixed', 'open', '2026-10-21 09:00:00', '2026-10-21 09:00:00'),
  (@client_b, (SELECT category_id FROM Category WHERE name = 'Digital Marketing'), 'FreelanceOS Demo - Organic search campaign', 'Prepare a technical SEO review, topic map, and four search-focused articles for an education service.', 900.00, 1500.00, '2026-12-20', 'fixed', 'open', '2026-10-22 09:00:00', '2026-10-22 09:00:00'),
  (@client_b, (SELECT category_id FROM Category WHERE name = 'Data Science'), 'FreelanceOS Demo - Customer support portal', 'Create a first-release support portal with a searchable help center and simple resolution analytics.', 2500.00, 3800.00, '2027-01-30', 'hourly', 'draft', '2026-10-24 09:00:00', '2026-10-24 09:00:00');

SET @project_active = (SELECT project_id FROM Project WHERE client_id = @client_a AND title = 'FreelanceOS Demo - Analytics dashboard refresh');
SET @project_complete = (SELECT project_id FROM Project WHERE client_id = @client_b AND title = 'FreelanceOS Demo - Product launch design system');
SET @project_mobile = (SELECT project_id FROM Project WHERE client_id = @client_a AND title = 'FreelanceOS Demo - Mobile onboarding experience');
SET @project_marketing = (SELECT project_id FROM Project WHERE client_id = @client_b AND title = 'FreelanceOS Demo - Organic search campaign');
SET @project_draft = (SELECT project_id FROM Project WHERE client_id = @client_b AND title = 'FreelanceOS Demo - Customer support portal');

INSERT INTO Project_Skill (project_id, skill_id)
SELECT @project_active, skill_id FROM Skill WHERE name IN ('Python', 'Flask', 'MySQL', 'JavaScript', 'Data Analysis');
INSERT INTO Project_Skill (project_id, skill_id)
SELECT @project_complete, skill_id FROM Skill WHERE name IN ('Figma', 'UI/UX', 'HTML/CSS');
INSERT INTO Project_Skill (project_id, skill_id)
SELECT @project_mobile, skill_id FROM Skill WHERE name IN ('JavaScript', 'React', 'UI/UX', 'Figma');
INSERT INTO Project_Skill (project_id, skill_id)
SELECT @project_marketing, skill_id FROM Skill WHERE name IN ('SEO', 'Content Writing', 'Data Analysis');
INSERT INTO Project_Skill (project_id, skill_id)
SELECT @project_draft, skill_id FROM Skill WHERE name IN ('Python', 'MySQL', 'Data Analysis');

INSERT INTO Application (project_id, freelancer_id, proposal, bid_amount, estimated_days, status, applied_at) VALUES
  (@project_active, @freelancer_a, 'I will build the dashboard as accessible components, connect the reporting queries, and document the API handoff.', 6200.00, 42, 'accepted', '2026-09-28 10:15:00'),
  (@project_complete, @freelancer_b, 'I can deliver the visual system, responsive landing page, and reusable Figma components for the launch.', 3600.00, 28, 'accepted', '2026-07-25 11:20:00'),
  (@project_mobile, @freelancer_a, 'I will map the onboarding steps, implement the responsive screens, and test the main account flow.', 2400.00, 18, 'pending', '2026-10-22 12:00:00'),
  (@project_mobile, @freelancer_b, 'I can provide interaction prototypes and a polished mobile-first interface ready for implementation.', 2600.00, 20, 'shortlisted', '2026-10-23 09:30:00'),
  (@project_marketing, @freelancer_b, 'I can review the site structure and create the topic map and article outlines.', 1200.00, 15, 'rejected', '2026-10-23 14:10:00'),
  (@project_marketing, @freelancer_c, 'I will deliver an SEO audit, prioritized topic plan, and four researched articles with on-page recommendations.', 1350.00, 18, 'pending', '2026-10-24 16:45:00');

SET @application_active = (SELECT application_id FROM Application WHERE project_id = @project_active AND freelancer_id = @freelancer_a);
SET @application_complete = (SELECT application_id FROM Application WHERE project_id = @project_complete AND freelancer_id = @freelancer_b);

-- Insert both contracts while their projects are in_progress and applications accepted.
INSERT INTO Contract (project_id, application_id, start_date, end_date, agreed_amount, status, created_at) VALUES
  (@project_active, @application_active, '2026-10-02', NULL, 6200.00, 'active', '2026-10-02 09:00:00'),
  (@project_complete, @application_complete, '2026-08-01', NULL, 3600.00, 'active', '2026-08-01 09:00:00');
SET @contract_active = (SELECT contract_id FROM Contract WHERE project_id = @project_active);
SET @contract_complete = (SELECT contract_id FROM Contract WHERE project_id = @project_complete);

INSERT INTO Task (contract_id, title, description, assigned_to, due_date, status, created_at) VALUES
  (@contract_active, 'Confirm dashboard metrics', 'Agree the KPI definitions and compare them with the current reporting view.', @freelancer_a, '2026-10-28', 'completed', '2026-10-03 09:00:00'),
  (@contract_active, 'Implement filterable charts', 'Connect the dashboard controls to parameterized project and payment queries.', @freelancer_a, '2026-11-12', 'in_progress', '2026-10-05 09:00:00'),
  (@contract_active, 'Submit accessibility review', 'Check keyboard operation, labels, contrast, and chart summaries.', @freelancer_a, '2026-11-18', 'submitted', '2026-10-07 09:00:00'),
  (@contract_active, 'Prepare handoff documentation', 'Document dashboard setup and provide a short deployment handoff.', @freelancer_a, '2026-12-10', 'todo', '2026-10-08 09:00:00'),
  (@contract_complete, 'Create product visual direction', 'Present the approved color, type, and component direction.', @freelancer_b, '2026-08-18', 'completed', '2026-08-02 09:00:00'),
  (@contract_complete, 'Deliver responsive launch page', 'Complete desktop and mobile layouts with production-ready handoff notes.', @freelancer_b, '2026-09-20', 'completed', '2026-08-10 09:00:00');

INSERT INTO Milestone (contract_id, title, description, amount, due_date, status, submitted_at, reviewed_at) VALUES
  (@contract_active, 'Discovery and dashboard plan', 'Metric definitions, screen outline, and data requirements.', 1500.00, '2026-10-15', 'approved', '2026-10-12 15:00:00', '2026-10-14 11:00:00'),
  (@contract_active, 'Charts and filter controls', 'Working dashboard charts and saved filter behavior.', 2000.00, '2026-11-20', 'submitted', '2026-10-23 16:00:00', NULL),
  (@contract_active, 'Final integration and handoff', 'Accessibility review, integration fixes, and handoff notes.', 1500.00, '2026-12-18', 'pending', NULL, NULL),
  (@contract_active, 'Accessibility and usability review', 'Approved keyboard, contrast, and chart-summary review.', 1200.00, '2026-12-01', 'approved', '2026-10-20 14:00:00', '2026-10-22 10:00:00'),
  (@contract_complete, 'Visual system and prototypes', 'Approved reusable visual components and responsive prototypes.', 1600.00, '2026-08-25', 'approved', '2026-08-22 13:00:00', '2026-08-24 10:00:00'),
  (@contract_complete, 'Launch page and final handoff', 'Completed responsive page and final design handoff.', 2000.00, '2026-09-28', 'approved', '2026-09-24 15:30:00', '2026-09-26 12:00:00');

SET @active_paid_milestone = (SELECT milestone_id FROM Milestone WHERE contract_id = @contract_active AND title = 'Discovery and dashboard plan');
SET @complete_milestone_a = (SELECT milestone_id FROM Milestone WHERE contract_id = @contract_complete AND title = 'Visual system and prototypes');
SET @complete_milestone_b = (SELECT milestone_id FROM Milestone WHERE contract_id = @contract_complete AND title = 'Launch page and final handoff');

-- Payment triggers require new payment rows to start pending; completed rows are
-- advanced afterward with unique demo references and their original amounts.
INSERT INTO Payment (contract_id, milestone_id, payer_id, payee_id, amount, status, payment_method, transaction_reference, paid_at, created_at) VALUES
  (@contract_active, @active_paid_milestone, @client_a, @freelancer_a, 1500.00, 'pending', 'demo', NULL, NULL, '2026-10-15 11:00:00'),
  (@contract_active, NULL, @client_a, @freelancer_a, 500.00, 'pending', 'demo', NULL, NULL, '2026-10-20 11:00:00'),
  (@contract_complete, @complete_milestone_a, @client_b, @freelancer_b, 1600.00, 'pending', 'demo', NULL, NULL, '2026-08-25 11:00:00'),
  (@contract_complete, @complete_milestone_b, @client_b, @freelancer_b, 2000.00, 'pending', 'demo', NULL, NULL, '2026-09-27 11:00:00');

UPDATE Payment SET status = 'completed', transaction_reference = 'DEMO-PAY-001', paid_at = '2026-10-15 11:30:00'
WHERE contract_id = @contract_active AND milestone_id = @active_paid_milestone;
UPDATE Milestone SET status = 'paid', reviewed_at = '2026-10-15 11:30:00'
WHERE milestone_id = @active_paid_milestone;

UPDATE Payment SET status = 'completed', transaction_reference = 'DEMO-PAY-002', paid_at = '2026-08-25 12:00:00'
WHERE contract_id = @contract_complete AND milestone_id = @complete_milestone_a;
UPDATE Payment SET status = 'completed', transaction_reference = 'DEMO-PAY-003', paid_at = '2026-09-27 12:00:00'
WHERE contract_id = @contract_complete AND milestone_id = @complete_milestone_b;
UPDATE Milestone SET status = 'paid', reviewed_at = '2026-08-25 12:00:00' WHERE milestone_id = @complete_milestone_a;
UPDATE Milestone SET status = 'paid', reviewed_at = '2026-09-27 12:00:00' WHERE milestone_id = @complete_milestone_b;
UPDATE Contract SET status = 'completed', end_date = '2026-09-29' WHERE contract_id = @contract_complete;
UPDATE Project SET status = 'completed', updated_at = '2026-09-29 12:00:00' WHERE project_id = @project_complete;

INSERT INTO Review (contract_id, reviewer_id, reviewee_id, rating, comment, created_at) VALUES
  (@contract_complete, @client_b, @freelancer_b, 5, 'Thoughtful design work, clear communication, and a smooth final handoff.', '2026-09-30 10:00:00'),
  (@contract_complete, @freelancer_b, @client_b, 5, 'Clear goals and timely feedback made the project straightforward to deliver.', '2026-09-30 10:10:00');

INSERT INTO Message (contract_id, sender_id, receiver_id, body, sent_at, read_at) VALUES
  (@contract_active, @client_a, @freelancer_a, 'The first dashboard milestone is approved. Please continue with the filter controls.', '2026-10-15 12:00:00', '2026-10-15 12:10:00'),
  (@contract_active, @freelancer_a, @client_a, 'Thanks. I have shared the chart preview and accessibility checklist for review.', '2026-10-23 16:10:00', NULL),
  (@contract_complete, @client_b, @freelancer_b, 'The launch page looks great. The final handoff is complete.', '2026-09-29 14:00:00', '2026-09-29 14:05:00');

INSERT INTO Notification (user_id, message, notification_type, is_read, created_at) VALUES
  (@freelancer_a, 'FreelanceOS demo: your application was accepted.', 'application_status', TRUE, '2026-10-02 09:10:00'),
  (@client_a, 'FreelanceOS demo: a milestone is ready for review.', 'milestone_submitted', FALSE, '2026-10-23 16:00:00'),
  (@freelancer_a, 'FreelanceOS demo: milestone payment completed.', 'payment_completed', TRUE, '2026-10-15 11:30:00'),
  (@client_a, 'FreelanceOS demo: a new message is waiting.', 'message_received', FALSE, '2026-10-23 16:10:00'),
  (@freelancer_b, 'FreelanceOS demo: your contract is complete.', 'contract_completed', TRUE, '2026-09-29 12:00:00'),
  (@client_b, 'FreelanceOS demo: your contract is complete.', 'contract_completed', TRUE, '2026-09-29 12:00:00'),
  (@freelancer_c, 'A client has shortlisted your mobile onboarding proposal.', 'application_status', FALSE, '2026-10-23 09:35:00');

INSERT INTO Dispute (contract_id, opened_by, reason, description, status, admin_id, resolution, created_at, resolved_at) VALUES
  (@contract_complete, @client_b, 'Launch asset scope clarification', 'Historical demo case: one final social banner was added after the original design handoff.', 'resolved', @admin, 'The extra banner was agreed as follow-up work outside the completed contract.', '2026-09-27 09:00:00', '2026-09-28 15:00:00');

COMMIT;
