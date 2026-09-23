CREATE TABLE identity_mappings (
  mapping_id VARCHAR(36) NOT NULL,                    
  lif_organization_id VARCHAR(255) NOT NULL,
  lif_organization_person_id VARCHAR(255) NOT NULL,                                                   
  target_system_id VARCHAR(255) NOT NULL,
  target_system_person_id_type VARCHAR(100) NOT NULL,                                      
  target_system_person_id VARCHAR(255) NOT NULL,                                      
  PRIMARY KEY (mapping_id),
  CONSTRAINT uq_identity_mapping UNIQUE(lif_organization_id, lif_organization_person_id, target_system_id, target_system_person_id_type),                                   
  -- Serves read_by_lif_org_and_person, the only table-size-sensitive read (the GET handler and
  -- the save pre-read). uq_identity_mapping cannot: its four key columns total 3460 bytes, over
  -- InnoDB's 3072-byte B-tree key limit, so MariaDB silently degrades it to USING HASH, which
  -- the optimizer can never use -- every lookup was a full table scan (#1231).
  --
  -- WIDTH IS LOAD-BEARING: 2 * 255 chars * 4 bytes (utf8mb4) = 3060 bytes, only 12 bytes under
  -- the same 3072-byte limit. Widening either column, or adding a third to this index, pushes it
  -- over and MariaDB will silently degrade this index to HASH too -- no error, just the full
  -- scans coming back. Verify with SHOW INDEX (Index_type must read BTREE) on a POPULATED table;
  -- EXPLAIN on an empty table reports key=NULL either way and cannot tell you.
  INDEX idx_org_person (lif_organization_id, lif_organization_person_id)
);
