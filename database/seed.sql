-- Small, deterministic demonstration dataset. Password hashes are placeholders;
-- replace them with real Werkzeug-generated hashes before using an application.
USE freelancer_pms;

INSERT INTO `User` (user_id, email, password_hash, full_name, role) VALUES
  (1, 'client@example.test', 'replace-with-password-hash', 'Avery Client', 'client'),
  (2, 'freelancer@example.test', 'replace-with-password-hash', 'Jordan Freelancer', 'freelancer'),
  (3, 'admin@example.test', 'replace-with-password-hash', 'Morgan Admin', 'admin'),
  (4, 'freelancer2@example.test', 'replace-with-password-hash', 'Taylor Designer', 'freelancer');

INSERT INTO Client (user_id, company_name, bio, location) VALUES
  (1, 'Northstar Studio', 'Small product design company', 'Toronto');

INSERT INTO Freelancer (user_id, headline, bio, hourly_rate, experience_years, location) VALUES
  (2, 'Full-stack web developer', 'Builds accessible business websites.', 55.00, 5, 'Toronto'),
  (4, 'UI/UX designer', 'Designs clear web and mobile experiences.', 48.00, 4, 'Montreal');

INSERT INTO Skill (skill_id, name) VALUES
  (1, 'Python'), (2, 'Flask'), (3, 'MySQL'), (4, 'Figma'), (5, 'JavaScript');

INSERT INTO Freelancer_Skill (freelancer_id, skill_id, proficiency_level) VALUES
  (2, 1, 5), (2, 2, 4), (2, 3, 4), (2, 5, 4), (4, 4, 5), (4, 5, 3);

INSERT INTO Portfolio (portfolio_id, freelancer_id, title, description, project_url) VALUES
  (1, 2, 'Inventory dashboard', 'A sample reporting dashboard.', 'https://example.test/portfolio/inventory'),
  (2, 4, 'Mobile banking concept', 'A sample interface concept.', 'https://example.test/portfolio/banking');

INSERT INTO Category (category_id, name, description) VALUES
  (1, 'Web Development', 'Websites and web applications'),
  (2, 'Design', 'User experience and visual design');

INSERT INTO Project (project_id, client_id, category_id, title, description, budget_min, budget_max, deadline, project_type, status) VALUES
  (1, 1, 1, 'Build a project tracker', 'Create a responsive project tracking web application.', 1500.00, 2500.00, '2026-12-15', 'fixed', 'in_progress'),
  (2, 1, 2, 'Design a landing page', 'Create a landing page design and handoff assets.', 500.00, 900.00, '2026-11-30', 'fixed', 'open'),
  (3, 1, 2, 'Design a product launch kit', 'Create a completed set of launch visuals for a sample product.', 400.00, 500.00, '2026-08-25', 'fixed', 'in_progress');

INSERT INTO Project_Skill (project_id, skill_id) VALUES
  (1, 1), (1, 2), (1, 3), (2, 4), (3, 4), (3, 5);

INSERT INTO Application (application_id, project_id, freelancer_id, proposal, bid_amount, estimated_days, status) VALUES
  (1, 1, 2, 'I can deliver the application in milestones with a maintainable Flask API.', 2200.00, 30, 'accepted'),
  (2, 2, 4, 'I can provide wireframes and a polished responsive visual design.', 750.00, 12, 'pending'),
  (3, 3, 4, 'I delivered a cohesive launch kit with web and social assets.', 450.00, 10, 'accepted');

INSERT INTO Contract (contract_id, project_id, application_id, start_date, end_date, agreed_amount, status) VALUES
  (1, 1, 1, '2026-09-01', NULL, 2200.00, 'active'),
  (2, 3, 3, '2026-08-01', NULL, 450.00, 'active');

INSERT INTO Task (task_id, contract_id, title, description, assigned_to, due_date, status) VALUES
  (1, 1, 'Design database schema', 'Prepare normalized tables and relationships.', 2, '2026-10-05', 'completed'),
  (2, 1, 'Implement project API', 'Create project endpoints and validation.', 2, '2026-11-01', 'in_progress'),
  (3, 2, 'Prepare launch graphics', 'Deliver final approved product launch visuals.', 4, '2026-08-20', 'completed');

INSERT INTO Milestone (milestone_id, contract_id, title, description, amount, due_date, status) VALUES
  (1, 1, 'Database and API foundation', 'Schema and initial API implementation.', 800.00, '2026-10-31', 'submitted'),
  (2, 1, 'Frontend integration', 'Integrate the UI with the project API.', 1400.00, '2026-12-15', 'pending'),
  (3, 2, 'Final launch kit', 'Approved final delivery for the product launch.', 450.00, '2026-08-25', 'approved');

INSERT INTO Payment (payment_id, contract_id, milestone_id, payer_id, payee_id, amount, status, payment_method, transaction_reference, paid_at) VALUES
  (1, 1, NULL, 1, 2, 300.00, 'pending', 'demo', NULL, NULL),
  (2, 2, 3, 1, 4, 450.00, 'pending', 'demo', NULL, NULL);

UPDATE Payment SET status = 'completed', transaction_reference = 'DEMO-TRANSFER-002', paid_at = '2026-08-25 12:00:00'
WHERE payment_id = 2;
UPDATE Milestone SET status = 'paid' WHERE milestone_id = 3;
UPDATE Contract SET status = 'completed', end_date = '2026-08-25' WHERE contract_id = 2;
UPDATE Project SET status = 'completed' WHERE project_id = 3;

INSERT INTO Review (review_id, contract_id, reviewer_id, reviewee_id, rating, comment) VALUES
  (1, 2, 1, 4, 5, 'Great collaboration and polished final delivery.');

INSERT INTO Message (message_id, contract_id, sender_id, receiver_id, body) VALUES
  (1, 1, 1, 2, 'Please share the milestone update when ready.'),
  (2, 1, 2, 1, 'The first milestone is ready for review.');

INSERT INTO Notification (notification_id, user_id, message, notification_type) VALUES
  (1, 1, 'A milestone was submitted for review.', 'milestone_submitted'),
  (2, 2, 'Your application was accepted.', 'application_accepted');

INSERT INTO Dispute (dispute_id, contract_id, opened_by, reason, description, status, admin_id) VALUES
  (1, 1, 1, 'Schedule clarification', 'Demo dispute record for admin review workflow.', 'investigating', 3);
