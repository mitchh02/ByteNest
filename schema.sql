-- Six Degrees Hiring - MySQL schema (MySQL 8.0.16+ for CHECK constraints)

CREATE DATABASE IF NOT EXISTS six_degrees
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE six_degrees;

-- People: profile, bio and current job title
CREATE TABLE users (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  first_name     VARCHAR(100)  NOT NULL,
  last_name      VARCHAR(100)  NOT NULL,
  email          VARCHAR(255)  NOT NULL UNIQUE,      -- login + primary contact
  password_hash  VARCHAR(255)  NULL,                 -- NULL for seeded demo users
  job_title      VARCHAR(150)  NULL,
  company        VARCHAR(150)  NULL,
  bio            TEXT          NULL,
  location       VARCHAR(150)  NULL,
  is_hiring      BOOLEAN       NOT NULL DEFAULT FALSE,
  created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_users_job_title (job_title),
  INDEX idx_users_hiring (is_hiring)
);

-- Contact info: any number of methods per user (phone, LinkedIn, GitHub, ...)
CREATE TABLE user_contacts (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  contact_type  ENUM('phone', 'email', 'linkedin', 'github', 'website', 'other') NOT NULL,
  value         VARCHAR(255) NOT NULL,
  is_public     BOOLEAN      NOT NULL DEFAULT FALSE,  -- private until an intro is accepted
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_contact (user_id, contact_type, value)
);

-- Connections: one row per pair, stored with the smaller id first
CREATE TABLE user_connections (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_a_id   INT UNSIGNED  NOT NULL,
  user_b_id   INT UNSIGNED  NOT NULL,
  strength    DECIMAL(3,2)  NOT NULL DEFAULT 0.50,   -- 0.01 to 1.00, used as Dijkstra weight
  source      ENUM('self_rated', 'coworker', 'github', 'contacts', 'inferred') NOT NULL DEFAULT 'self_rated',
  context     VARCHAR(255)  NULL,                    -- "worked together at Acme, 2021-2024"
  confirmed   BOOLEAN       NOT NULL DEFAULT FALSE,  -- both people agreed
  created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_a_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (user_b_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_pair (user_a_id, user_b_id),
  INDEX idx_conn_b (user_b_id),
  CONSTRAINT chk_order    CHECK (user_a_id < user_b_id),
  CONSTRAINT chk_strength CHECK (strength > 0 AND strength <= 1)
);

-- Open roles posted by hiring users (what job seekers search for)
CREATE TABLE job_openings (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  posted_by    INT UNSIGNED NOT NULL,
  title        VARCHAR(150) NOT NULL,
  company      VARCHAR(150) NOT NULL,
  description  TEXT         NULL,
  is_open      BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_jobs_title (title),
  FULLTEXT INDEX ft_jobs (title, description)
);


-- ---------------------------------------------------------------
-- Handy queries
-- ---------------------------------------------------------------

-- Load every edge into NetworkX for Dijkstra:
--   SELECT user_a_id, user_b_id, strength, context FROM user_connections;

-- Add a connection (always pass the smaller id first):
--   INSERT INTO user_connections (user_a_id, user_b_id, strength, source, context)
--   VALUES (LEAST(12, 7), GREATEST(12, 7), 0.80, 'coworker', 'Same team at Acme')
--   ON DUPLICATE KEY UPDATE strength = VALUES(strength), context = VALUES(context);

-- All of one user's connections:
--   SELECT u.id, u.first_name, u.last_name, u.job_title, c.strength, c.context
--   FROM user_connections c
--   JOIN users u ON u.id = IF(c.user_a_id = 7, c.user_b_id, c.user_a_id)
--   WHERE 7 IN (c.user_a_id, c.user_b_id);

-- Hiring managers for a role search:
--   SELECT j.id, j.title, j.company, j.posted_by
--   FROM job_openings j
--   WHERE j.is_open AND MATCH(j.title, j.description) AGAINST ('backend engineer');
