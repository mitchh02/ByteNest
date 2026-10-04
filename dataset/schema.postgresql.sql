BEGIN;

CREATE SCHEMA IF NOT EXISTS professional_network;

SET search_path TO professional_network, public;

CREATE TABLE dataset_batches (
  batch_id TEXT NOT NULL,
  created_on DATE NOT NULL,
  schema_version TEXT NOT NULL,
  max_total_hops INTEGER NOT NULL,
  status TEXT NOT NULL,
  weight_policy TEXT NOT NULL,
  PRIMARY KEY (batch_id)
);

CREATE TABLE organizations (
  organization_id TEXT NOT NULL,
  name TEXT NOT NULL,
  official_domain TEXT NOT NULL,
  organization_kind TEXT NOT NULL,
  PRIMARY KEY (organization_id)
);

CREATE TABLE sources (
  source_id TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  publisher_domain TEXT NOT NULL,
  source_type TEXT NOT NULL,
  published_on DATE,
  publication_year INTEGER,
  publication_date_precision TEXT NOT NULL,
  checked_on DATE NOT NULL,
  retrieval_scope TEXT NOT NULL,
  batch_id TEXT NOT NULL REFERENCES dataset_batches(batch_id),
  PRIMARY KEY (source_id),
  UNIQUE (url)
);

CREATE TABLE people (
  person_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  identity_source_id TEXT NOT NULL REFERENCES sources(source_id),
  identity_status TEXT NOT NULL,
  first_checked_on DATE NOT NULL,
  batch_id TEXT NOT NULL REFERENCES dataset_batches(batch_id),
  PRIMARY KEY (person_id)
);

CREATE TABLE person_aliases (
  alias_id TEXT NOT NULL,
  person_id TEXT NOT NULL REFERENCES people(person_id),
  alias TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  PRIMARY KEY (alias_id)
);

CREATE TABLE roles (
  role_id TEXT NOT NULL,
  person_id TEXT NOT NULL REFERENCES people(person_id),
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  role_label TEXT NOT NULL,
  role_category TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  observed_on DATE,
  observation_year INTEGER,
  observation_date_precision TEXT NOT NULL,
  observation_scope TEXT NOT NULL,
  hiring_authority TEXT NOT NULL,
  checked_on DATE NOT NULL,
  PRIMARY KEY (role_id)
);

CREATE TABLE nets (
  net_id TEXT NOT NULL,
  label TEXT NOT NULL,
  organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
  membership_policy TEXT NOT NULL,
  path_policy TEXT NOT NULL,
  batch_id TEXT NOT NULL REFERENCES dataset_batches(batch_id),
  PRIMARY KEY (net_id)
);

CREATE TABLE net_targets (
  net_id TEXT NOT NULL REFERENCES nets(net_id),
  person_id TEXT NOT NULL REFERENCES people(person_id),
  role_id TEXT NOT NULL REFERENCES roles(role_id),
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  target_scope TEXT NOT NULL,
  PRIMARY KEY (net_id, person_id)
);

CREATE TABLE evidence_claims (
  claim_id TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  claim_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  locator TEXT NOT NULL,
  observed_on DATE,
  observation_year INTEGER,
  observation_date_precision TEXT NOT NULL,
  checked_on DATE NOT NULL,
  PRIMARY KEY (claim_id)
);

CREATE TABLE relationships (
  relationship_id TEXT NOT NULL,
  person_a_id TEXT NOT NULL REFERENCES people(person_id),
  person_b_id TEXT NOT NULL REFERENCES people(person_id),
  relationship_type TEXT NOT NULL,
  context TEXT NOT NULL,
  manager_person_id TEXT REFERENCES people(person_id),
  closeness TEXT NOT NULL,
  routing_weight DOUBLE PRECISION NOT NULL,
  weight_semantics TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  temporal_scope TEXT NOT NULL,
  relationship_start_year INTEGER,
  relationship_end_year INTEGER,
  strict_net_eligible BOOLEAN NOT NULL,
  last_checked_on DATE NOT NULL,
  batch_id TEXT NOT NULL REFERENCES dataset_batches(batch_id),
  PRIMARY KEY (relationship_id),
  CHECK (person_a_id < person_b_id),
  CHECK (routing_weight > 0 AND routing_weight <= 1),
  CHECK (manager_person_id IS NULL OR manager_person_id IN (person_a_id, person_b_id)),
  UNIQUE (person_a_id, person_b_id, relationship_type, context)
);

CREATE TABLE relationship_evidence (
  relationship_id TEXT NOT NULL REFERENCES relationships(relationship_id),
  claim_id TEXT NOT NULL REFERENCES evidence_claims(claim_id),
  support_basis TEXT NOT NULL,
  PRIMARY KEY (relationship_id, claim_id)
);

CREATE TABLE route_cache (
  route_id TEXT NOT NULL,
  net_id TEXT NOT NULL REFERENCES nets(net_id),
  entry_person_id TEXT NOT NULL REFERENCES people(person_id),
  target_person_id TEXT NOT NULL REFERENCES people(person_id),
  hop_count INTEGER NOT NULL,
  person_ids JSONB NOT NULL,
  relationship_ids JSONB NOT NULL,
  policy_weight_product DOUBLE PRECISION NOT NULL,
  negative_log_weight DOUBLE PRECISION NOT NULL,
  built_on DATE NOT NULL,
  batch_id TEXT NOT NULL REFERENCES dataset_batches(batch_id),
  PRIMARY KEY (route_id),
  CHECK (hop_count BETWEEN 0 AND 6),
  UNIQUE (net_id, entry_person_id, target_person_id, hop_count)
);

CREATE TABLE expansion_queue (
  task_id TEXT NOT NULL,
  anchor_person_id TEXT NOT NULL REFERENCES people(person_id),
  priority INTEGER NOT NULL,
  search_query TEXT NOT NULL,
  focus TEXT NOT NULL,
  status TEXT NOT NULL,
  admission_rule TEXT NOT NULL,
  batch_id TEXT NOT NULL REFERENCES dataset_batches(batch_id),
  PRIMARY KEY (task_id)
);

CREATE INDEX idx_81c197f1cf6bd123 ON people (display_name);

CREATE INDEX idx_f44606acbc53a983 ON person_aliases (alias);

CREATE INDEX idx_6c15921a86dd3c04 ON roles (organization_id, role_category);

CREATE INDEX idx_081d85a4780e2bd6 ON relationships (person_a_id);

CREATE INDEX idx_66dc5b84c2f5ca5c ON relationships (person_b_id);

CREATE INDEX idx_3e93ed9c3ed9a1b2 ON relationship_evidence (claim_id);

CREATE INDEX idx_ab46cbb5d40cf556 ON route_cache (entry_person_id, net_id, hop_count);

CREATE INDEX idx_2f860d9d747c1eae ON route_cache (target_person_id, hop_count);

CREATE INDEX idx_dc411c70806b38a4 ON expansion_queue (status, priority);

CREATE VIEW strict_edges AS SELECT * FROM relationships WHERE strict_net_eligible = TRUE AND verification_status = 'source_supported';

CREATE VIEW network_entries AS SELECT net_id, entry_person_id, MIN(hop_count) AS min_hops_to_any_target, MAX(policy_weight_product) AS best_policy_weight_product FROM route_cache GROUP BY net_id, entry_person_id;

COMMIT;
