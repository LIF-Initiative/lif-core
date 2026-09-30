CREATE TABLE identity_mappings (
  mapping_id VARCHAR(36) NOT NULL,                    
  lif_organization_id VARCHAR(191) NOT NULL,
  lif_organization_person_id VARCHAR(191) NOT NULL,                                                   
  target_system_id VARCHAR(191) NOT NULL,
  target_system_person_id_type VARCHAR(100) NOT NULL,                                      
  target_system_person_id VARCHAR(255) NOT NULL,                                      
  PRIMARY KEY (mapping_id),
  -- Also serves read_by_lif_org_and_person (the GET handler and the save pre-read) as a
  -- leftmost prefix, so no separate org/person index is needed (#1258).
  --
  -- WIDTH IS LOAD-BEARING: (191 * 3 + 100) chars * 4 bytes (utf8mb4) = 2692 bytes, under
  -- InnoDB's 3072-byte B-tree key limit. At 255 the key was 3460 bytes: MariaDB silently
  -- degraded it to USING HASH, which the optimizer can never read through -- every lookup was
  -- a full table scan (#1231) -- and MySQL 8 rejected this CREATE TABLE outright. Widening any
  -- key column, or adding one to the key, can push it back over with no error. Verify with
  -- SHOW INDEX (Index_type must read BTREE) on a POPULATED table; EXPLAIN on an empty table
  -- reports key=NULL either way and cannot tell you.
  CONSTRAINT uq_identity_mapping UNIQUE(lif_organization_id, lif_organization_person_id, target_system_id, target_system_person_id_type)
);
