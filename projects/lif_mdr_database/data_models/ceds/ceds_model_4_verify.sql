-- Verification for the CEDS v14 (DataModelId 4) rebuild: the counts and structural checks listed under
-- "Verification" in README.md beside this file. Every row prints check / expected / actual; a build passes
-- when every "ok" column is true.
-- cspell:ignore ceds
SET search_path TO public;
WITH live_e AS (SELECT * FROM "Entities" WHERE "DataModelId" = 4 AND "Deleted" IS NOT TRUE),
     live_a AS (SELECT * FROM "Attributes" WHERE "DataModelId" = 4 AND "Deleted" IS NOT TRUE),
     live_ea AS (SELECT ea.* FROM "EntityAssociation" ea JOIN live_e p ON p."Id" = ea."ParentEntityId" WHERE ea."Deleted" IS NOT TRUE),
     live_eaa AS (SELECT x.* FROM "EntityAttributeAssociation" x JOIN live_e p ON p."Id" = x."EntityId" WHERE x."Deleted" IS NOT TRUE),
     live_vs AS (SELECT * FROM "ValueSets" WHERE "DataModelId" = 4 AND "Deleted" IS NOT TRUE),
     ceds_vs AS (SELECT * FROM live_vs WHERE "Notes" LIKE 'scheme: %'),
     ceds_vsv AS (SELECT v.* FROM "ValueSetValues" v JOIN ceds_vs s ON s."Id" = v."ValueSetId" WHERE v."Deleted" IS NOT TRUE),
     keys AS (SELECT "EntityId" AS parent, "Name" FROM live_eaa UNION ALL SELECT "ParentEntityId", "Name" FROM live_ea),
     checks(ord, label, expected, actual) AS (
  SELECT 1, 'model: DataModels row 4 is CEDS v14 / 14.0.0.0', 1,
      (SELECT count(*) FROM "DataModels" WHERE "Id" = 4 AND "Name" = 'CEDS v14' AND "DataModelVersion" = '14.0.0.0' AND "Deleted" IS NOT TRUE AND "Notes" LIKE 'Tracks CEDS Ontology v14.0.0.0%')
  UNION ALL SELECT 2, 'count: entities live (one per CEDS class)', 402, (SELECT count(*) FROM live_e)
  UNION ALL SELECT 3, 'count: kept pre-build entity ids live', 6, (SELECT count(*) FROM live_e WHERE "Id" IN (14, 15, 18, 19, 198, 307))
  UNION ALL SELECT 4, 'count: retired pre-build entities', 19, (SELECT count(*) FROM "Entities" WHERE "DataModelId" = 4 AND "Deleted" IS TRUE AND "Id" IN (12, 13, 16, 17, 20, 54, 55, 56, 90, 91, 92, 93, 147, 148, 149, 221, 222, 264, 306))
  UNION ALL SELECT 5, 'count: ... with a replacement note', 12, (SELECT count(*) FROM "Entities" WHERE "DataModelId" = 4 AND "Deleted" IS TRUE AND "UseConsiderations" LIKE 'Retired. Replaced by CEDS v14 classes: %')
  UNION ALL SELECT 6, 'count: attributes live', 1973, (SELECT count(*) FROM live_a)
  UNION ALL SELECT 7, 'count: attributes enum', 994, (SELECT count(*) FROM live_a WHERE "DataType" = 'enum')
  UNION ALL SELECT 8, 'count: attributes string', 727, (SELECT count(*) FROM live_a WHERE "DataType" = 'string')
  UNION ALL SELECT 9, 'count: attributes number', 252, (SELECT count(*) FROM live_a WHERE "DataType" = 'number')
  UNION ALL SELECT 10, 'count: attribute associations', 2277, (SELECT count(*) FROM live_eaa)
  UNION ALL SELECT 11, 'count: attributes shared by several classes', 187, (SELECT count(*) FROM (SELECT 1 FROM live_eaa GROUP BY "AttributeId" HAVING count(*) > 1) s)
  UNION ALL SELECT 12, 'count: reference associations', 473, (SELECT count(*) FROM live_ea)
  UNION ALL SELECT 13, 'count: ... across properties', 351, (SELECT count(DISTINCT substring("Notes" from '^property: (P[0-9]+)')) FROM live_ea)
  UNION ALL SELECT 14, 'count: self references', 6, (SELECT count(*) FROM live_ea WHERE "ParentEntityId" = "ChildEntityId")
  UNION ALL SELECT 15, 'count: CEDS value sets', 965, (SELECT count(*) FROM ceds_vs)
  UNION ALL SELECT 16, 'count: CEDS values', 11810, (SELECT count(*) FROM ceds_vsv)
  UNION ALL SELECT 17, 'count: ISO6393LanguageCode values (capped, and says so)', 183,
      (SELECT count(*) FROM ceds_vsv v JOIN ceds_vs s ON s."Id" = v."ValueSetId" WHERE s."Name" = 'ISO6393LanguageCode' AND s."UseConsiderations" LIKE '%Capped: holds the 183 of the 7916%')
  UNION ALL SELECT 18, 'count: StateAbbreviation remediated in place (id 277, 65 values)', 65,
      (SELECT count(*) FROM ceds_vsv v WHERE v."ValueSetId" = 277)
  UNION ALL SELECT 19, 'count: live mappings on StateAbbreviation values kept', 62,
      (SELECT count(*) FROM "ValueSetValueMapping" m JOIN ceds_vsv v ON v."Id" = m."SourceValueId" WHERE v."ValueSetId" = 277 AND m."Deleted" IS NOT TRUE)
  UNION ALL SELECT 20, 'count: legacy value sets left as they were', 67, (SELECT count(*) FROM live_vs WHERE "Notes" IS NULL AND "Id" <= 489)
  UNION ALL SELECT 21, 'count: retired legacy value sets', 9, (SELECT count(*) FROM "ValueSets" WHERE "DataModelId" = 4 AND "Deleted" IS TRUE AND "Id" IN (38, 39, 40, 41, 73, 328, 331, 332, 333))
  UNION ALL SELECT 22, 'count: ... their values retired', 583, (SELECT count(*) FROM "ValueSetValues" WHERE "DataModelId" = 4 AND "Deleted" IS TRUE AND "ValueSetId" IN (38, 39, 40, 41, 73, 328, 331, 332, 333))
  UNION ALL SELECT 23, 'count: ... their mapping rows retired', 583,
      (SELECT count(*) FROM "ValueSetValueMapping" m JOIN "ValueSetValues" v ON v."Id" = m."SourceValueId" WHERE v."ValueSetId" IN (38, 39, 40, 41, 73, 328, 331, 332, 333) AND m."Deleted" IS TRUE)
  UNION ALL SELECT 24, 'count: live mapping rows into or out of a retired value', 0,
      (SELECT count(*) FROM "ValueSetValueMapping" m JOIN "ValueSetValues" v ON v."Id" IN (m."SourceValueId", m."TargetValueId") WHERE v."DataModelId" = 4 AND v."Deleted" IS TRUE AND m."Deleted" IS NOT TRUE)
  UNION ALL SELECT 25, 'count: old attributes retired', 187, (SELECT count(*) FROM "Attributes" WHERE "DataModelId" = 4 AND "Deleted" IS TRUE AND "Id" <= 1694)
  UNION ALL SELECT 26, 'deprecated: attributes', 2, (SELECT count(*) FROM live_a WHERE "DeprecationDate" = '2026-03-11T00:00:00Z' AND "UseConsiderations" LIKE '%Deprecated in CEDS: %')
  UNION ALL SELECT 27, 'deprecated: reference associations', 1, (SELECT count(*) FROM live_ea WHERE "DeprecationDate" = '2026-03-11T00:00:00Z' AND "Notes" LIKE '%Deprecated in CEDS: %')
  UNION ALL SELECT 28, 'deprecated: value sets', 1, (SELECT count(*) FROM ceds_vs WHERE "DeprecationDate" = '2026-03-11T00:00:00Z' AND "UseConsiderations" LIKE '%Deprecated in CEDS: %')
  UNION ALL SELECT 29, 'deprecated: values', 25, (SELECT count(*) FROM ceds_vsv WHERE "DeprecationDate" = '2026-03-11T00:00:00Z' AND "UseConsiderations" LIKE '%Deprecated in CEDS: %')
  UNION ALL SELECT 30, 'deprecated: anything else carrying a DeprecationDate', 0,
      (SELECT count(*) FROM live_e WHERE "DeprecationDate" IS NOT NULL) + (SELECT count(*) FROM live_eaa WHERE "DeprecationDate" IS NOT NULL)
  UNION ALL SELECT 31, 'group: CEDS_LIF (3) unchanged, one live transformation', 1,
      (SELECT count(*) FROM "Transformations" t JOIN "TransformationsGroup" g ON g."Id" = t."TransformationGroupId" WHERE g."Id" = 3 AND g."Deleted" IS NOT TRUE AND t."Deleted" IS NOT TRUE)
  UNION ALL SELECT 32, 'tenant: tenant_lif_team keeps its pre-build model 4', 25, (SELECT count(*) FROM tenant_lif_team."Entities" WHERE "DataModelId" = 4 AND "Deleted" IS NOT TRUE)
  UNION ALL SELECT 51, 'structure: duplicate entity UniqueName', 0, (SELECT count(*) FROM (SELECT 1 FROM live_e GROUP BY "UniqueName" HAVING count(*) > 1) d)
  UNION ALL SELECT 52, 'structure: entity Name <> UniqueName', 0, (SELECT count(*) FROM live_e WHERE "Name" <> "UniqueName")
  UNION ALL SELECT 53, 'structure: duplicate attribute UniqueName', 0, (SELECT count(*) FROM (SELECT 1 FROM live_a GROUP BY "UniqueName" HAVING count(*) > 1) d)
  UNION ALL SELECT 54, 'structure: attribute UniqueName <> Name (the _P###### pair)', 2, (SELECT count(*) FROM live_a WHERE "UniqueName" <> "Name")
  UNION ALL SELECT 55, 'structure: reference Names with a _P###### suffix', 2, (SELECT count(*) FROM live_ea WHERE "Name" ~ '_P[0-9]{6}$')
  UNION ALL SELECT 56, 'structure: a key used twice under one parent', 0, (SELECT count(*) FROM (SELECT 1 FROM keys GROUP BY parent, "Name" HAVING count(*) > 1) d)
  UNION ALL SELECT 57, 'structure: EAA Name <> attribute Name', 0, (SELECT count(*) FROM live_eaa x JOIN live_a a ON a."Id" = x."AttributeId" WHERE x."Name" IS DISTINCT FROM a."Name")
  UNION ALL SELECT 58, 'structure: associations with a NULL Name or Array', 0, (SELECT count(*) FROM live_ea WHERE "Name" IS NULL OR "Array" IS NULL) + (SELECT count(*) FROM live_eaa WHERE "Name" IS NULL OR "Array" IS NULL)
  UNION ALL SELECT 59, 'structure: associations with Array true (CEDS declares no cardinality)', 0, (SELECT count(*) FROM live_ea WHERE "Array") + (SELECT count(*) FROM live_eaa WHERE "Array")
  UNION ALL SELECT 60, 'structure: references not Placement Reference or with a Relationship', 0, (SELECT count(*) FROM live_ea WHERE "Placement" IS DISTINCT FROM 'Reference' OR "Relationship" IS NOT NULL)
  UNION ALL SELECT 61, 'structure: reference child outside the live model', 0, (SELECT count(*) FROM live_ea a WHERE NOT EXISTS (SELECT 1 FROM live_e e WHERE e."Id" = a."ChildEntityId"))
  UNION ALL SELECT 62, 'structure: attribute in no association', 0, (SELECT count(*) FROM live_a a WHERE NOT EXISTS (SELECT 1 FROM live_eaa x WHERE x."AttributeId" = a."Id"))
  UNION ALL SELECT 63, 'structure: Required or Array set on an entity or attribute', 0,
      (SELECT count(*) FROM live_e WHERE "Required" IS NOT NULL OR "Array" IS NOT NULL) + (SELECT count(*) FROM live_a WHERE "Required" IS NOT NULL OR "Array" IS NOT NULL)
  UNION ALL SELECT 64, 'structure: element flags NULL', 0,
      (SELECT count(*) FROM live_e WHERE "LevelOfAccess" IS NULL OR "Queryable" IS NULL OR "Modifiable" IS NULL) + (SELECT count(*) FROM live_a WHERE "LevelOfAccess" IS NULL OR "Queryable" IS NULL OR "Modifiable" IS NULL)
  UNION ALL SELECT 65, 'typing: NULL, entity or other DataType', 0, (SELECT count(*) FROM live_a WHERE "DataType" IS NULL OR "DataType" NOT IN ('enum', 'string', 'number'))
  UNION ALL SELECT 66, 'typing: attributes with a TargetEntityId', 0, (SELECT count(*) FROM live_a WHERE "TargetEntityId" IS NOT NULL)
  UNION ALL SELECT 67, 'typing: enum attributes without a ValueSetId', 0, (SELECT count(*) FROM live_a WHERE "DataType" = 'enum' AND "ValueSetId" IS NULL)
  UNION ALL SELECT 68, 'typing: non-enum attributes with a ValueSetId', 0, (SELECT count(*) FROM live_a WHERE "DataType" <> 'enum' AND "ValueSetId" IS NOT NULL)
  UNION ALL SELECT 69, 'typing: enum bound to a value set outside the CEDS schemes', 0, (SELECT count(*) FROM live_a a WHERE "ValueSetId" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ceds_vs s WHERE s."Id" = a."ValueSetId"))
  UNION ALL SELECT 70, 'values: duplicate ValueName within a CEDS value set', 0, (SELECT count(*) FROM (SELECT 1 FROM ceds_vsv GROUP BY "ValueSetId", "ValueName" HAVING count(*) > 1) d)
  UNION ALL SELECT 71, 'values: duplicate code within a CEDS value set', 0, (SELECT count(*) FROM (SELECT 1 FROM ceds_vsv GROUP BY "ValueSetId", "Value" HAVING count(*) > 1) d)
  UNION ALL SELECT 72, 'temp functions dropped', 0, (SELECT count(*) FROM pg_proc WHERE proname LIKE 'ceds_tmp_%')
)
SELECT ord, label, expected, actual, expected = actual AS ok FROM checks ORDER BY ord;
