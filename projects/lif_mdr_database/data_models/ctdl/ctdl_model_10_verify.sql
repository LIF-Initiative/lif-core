-- Verification for the CTDL (DataModelId 10) rebuild: the counts and structural checks listed under
-- "Verification" in README.md beside this file. Every row prints check / expected / actual; a build passes
-- when every "ok" column is true.
-- cspell:ignore ctdl
SET search_path TO public;
WITH live_e AS (SELECT * FROM "Entities" WHERE "DataModelId" = 10 AND "Deleted" IS NOT TRUE),
     live_a AS (SELECT * FROM "Attributes" WHERE "DataModelId" = 10 AND "Deleted" IS NOT TRUE),
     live_ea AS (SELECT ea.* FROM "EntityAssociation" ea JOIN live_e p ON p."Id" = ea."ParentEntityId" WHERE ea."Deleted" IS NOT TRUE),
     live_eaa AS (SELECT x.* FROM "EntityAttributeAssociation" x JOIN live_e p ON p."Id" = x."EntityId" WHERE x."Deleted" IS NOT TRUE),
     live_vs AS (SELECT * FROM "ValueSets" WHERE "DataModelId" = 10 AND "Deleted" IS NOT TRUE),
     live_vsv AS (SELECT v.* FROM "ValueSetValues" v JOIN live_vs s ON s."Id" = v."ValueSetId" WHERE v."Deleted" IS NOT TRUE),
     checks(ord, label, expected, actual) AS (
  SELECT 1, 'count: entities live', 142, (SELECT count(*) FROM live_e)
  UNION ALL SELECT 2, 'count: reference associations', 5402, (SELECT count(*) FROM live_ea)
  UNION ALL SELECT 3, 'count: attribute rows (7,753 - 5,402 + 10 retained)', 2361, (SELECT count(*) FROM live_a)
  UNION ALL SELECT 4, 'count: attribute associations', 2361, (SELECT count(*) FROM live_eaa)
  UNION ALL SELECT 5, 'count: entities with subClassOf notes', 96, (SELECT count(*) FROM live_e WHERE "Notes" LIKE '%subClassOf:%')
  UNION ALL SELECT 6, 'count: propertyless entities (no attribute, no reference out)', 10,
      (SELECT count(*) FROM live_e e WHERE NOT EXISTS (SELECT 1 FROM live_eaa x WHERE x."EntityId" = e."Id") AND NOT EXISTS (SELECT 1 FROM live_ea a WHERE a."ParentEntityId" = e."Id"))
  UNION ALL SELECT 7, 'count: value sets live', 36, (SELECT count(*) FROM live_vs)
  UNION ALL SELECT 8, 'count: value set values live', 457, (SELECT count(*) FROM live_vsv)
  UNION ALL SELECT 9, 'count: attribute Array = Yes (915 + 6 retained)', 921, (SELECT count(*) FROM live_a WHERE "Array" = 'Yes')
  UNION ALL SELECT 10, 'count: attribute Array = No (1,433 + 4 retained)', 1437, (SELECT count(*) FROM live_a WHERE "Array" = 'No')
  UNION ALL SELECT 11, 'count: attribute Array null', 3, (SELECT count(*) FROM live_a WHERE "Array" IS NULL)
  UNION ALL SELECT 12, 'count: attribute Array = Yes on domain rows only', 915, (SELECT count(*) FROM live_a WHERE "Array" = 'Yes' AND "UniqueName" NOT LIKE 'Competency.%' AND "UniqueName" NOT LIKE 'CompetencyFramework.%')
  UNION ALL SELECT 13, 'count: reference notes multivalue: true', 4929, (SELECT count(*) FROM live_ea WHERE "Notes" LIKE 'multivalue: true%')
  UNION ALL SELECT 14, 'count: reference notes multivalue: false', 321, (SELECT count(*) FROM live_ea WHERE "Notes" LIKE 'multivalue: false%')
  UNION ALL SELECT 15, 'count: reference notes multivalue: unknown', 152, (SELECT count(*) FROM live_ea WHERE "Notes" LIKE 'multivalue: unknown%')
  UNION ALL SELECT 16, 'count: rows with no resolvable range, typed string', 140, (SELECT count(*) FROM live_a WHERE "DataType" = 'string' AND "Notes" LIKE '%[out of model]%')
  UNION ALL SELECT 17, 'count: ... across properties', 13, (SELECT count(DISTINCT "Name") FROM live_a WHERE "DataType" = 'string' AND "Notes" LIKE '%[out of model]%')
  UNION ALL SELECT 18, 'count: reference rows carrying an unresolved range', 295, (SELECT count(*) FROM live_ea WHERE "Notes" LIKE '%unresolvedRanges:%')
  UNION ALL SELECT 19, 'count: ... across properties', 21, (SELECT count(DISTINCT "Name") FROM live_ea WHERE "Notes" LIKE '%unresolvedRanges:%')
  UNION ALL SELECT 20, 'count: attributes with null DataType', 0, (SELECT count(*) FROM live_a WHERE "DataType" IS NULL)
  UNION ALL SELECT 21, 'count: value-set links (rows)', 21, (SELECT count(*) FROM live_a WHERE "ValueSetId" IS NOT NULL)
  UNION ALL SELECT 22, 'count: value-set links (properties)', 16, (SELECT count(DISTINCT "Name") FROM live_a WHERE "ValueSetId" IS NOT NULL)
  UNION ALL SELECT 23, 'count: old value sets soft-deleted', 27, (SELECT count(*) FROM "ValueSets" WHERE "DataModelId" = 10 AND "Deleted" IS TRUE AND "Id" < 453)
  UNION ALL SELECT 24, 'count: old value set values soft-deleted', 112, (SELECT count(*) FROM "ValueSetValues" WHERE "DataModelId" = 10 AND "Deleted" IS TRUE AND "Id" < 7670)
  UNION ALL SELECT 25, 'count: mapping rows from old CTDL values soft-deleted', 115, (SELECT count(*) FROM "ValueSetValueMapping" m JOIN "ValueSetValues" v ON v."Id" = m."SourceValueId" WHERE v."DataModelId" = 10 AND m."Deleted" IS TRUE)
  UNION ALL SELECT 26, 'count: live mapping rows from CTDL values (the rebuilt AudienceLevel -> LIF set 52 crosswalk)', 7, (SELECT count(*) FROM "ValueSetValueMapping" m JOIN "ValueSetValues" v ON v."Id" = m."SourceValueId" JOIN "ValueSets" s ON s."Id" = v."ValueSetId" JOIN "ValueSetValues" t ON t."Id" = m."TargetValueId" WHERE v."DataModelId" = 10 AND s."Name" = 'AudienceLevel' AND t."ValueSetId" = 52 AND m."Deleted" IS NOT TRUE AND v."Deleted" IS NOT TRUE AND t."Deleted" IS NOT TRUE)
  UNION ALL SELECT 27, 'count: transformation group 9 deleted', 1, (SELECT count(*) FROM "TransformationsGroup" WHERE "Id" = 9 AND "Deleted" IS TRUE)
  UNION ALL SELECT 28, 'count: transformations in group 9 deleted', 176, (SELECT count(*) FROM "Transformations" WHERE "TransformationGroupId" = 9 AND "Deleted" IS TRUE)
  UNION ALL SELECT 29, 'count: transformation attributes in group 9 deleted', 352, (SELECT count(*) FROM "TransformationAttributes" ta JOIN "Transformations" t ON t."Id" = ta."TransformationId" WHERE t."TransformationGroupId" = 9 AND ta."Deleted" IS TRUE)
  UNION ALL SELECT 30, 'count: LIF value set 52 still live', 1, (SELECT count(*) FROM "ValueSets" WHERE "Id" = 52 AND "Deleted" IS NOT TRUE)
  UNION ALL SELECT 31, 'count: old entities 14 soft-deleted', 14, (SELECT count(*) FROM "Entities" WHERE "DataModelId" = 10 AND "Deleted" IS TRUE AND "Id" < 518)
  UNION ALL SELECT 32, 'count: old attributes 140 soft-deleted', 140, (SELECT count(*) FROM "Attributes" WHERE "DataModelId" = 10 AND "Deleted" IS TRUE AND "Id" < 3501)
  UNION ALL SELECT 33, 'structure: (parent, Name) duplicated among references', 0, (SELECT count(*) FROM (SELECT 1 FROM live_ea GROUP BY "ParentEntityId", "Name" HAVING count(*) > 1) d)
  UNION ALL SELECT 34, 'structure: (entity, Name) duplicated among attribute associations', 0, (SELECT count(*) FROM (SELECT 1 FROM live_eaa GROUP BY "EntityId", "Name" HAVING count(*) > 1) d)
  UNION ALL SELECT 35, 'structure: Name shared by a reference and an attribute on one entity', 0, (SELECT count(*) FROM live_ea a JOIN live_eaa x ON x."EntityId" = a."ParentEntityId" AND x."Name" = a."Name")
  UNION ALL SELECT 36, 'structure: duplicate (entity, attribute) associations', 0, (SELECT count(*) FROM (SELECT 1 FROM live_eaa GROUP BY "EntityId", "AttributeId" HAVING count(*) > 1) d)
  UNION ALL SELECT 37, 'structure: attributes with no association', 0, (SELECT count(*) FROM live_a a WHERE NOT EXISTS (SELECT 1 FROM live_eaa x WHERE x."AttributeId" = a."Id"))
  UNION ALL SELECT 38, 'structure: attributes shared by two entities', 0, (SELECT count(*) FROM (SELECT 1 FROM live_eaa GROUP BY "AttributeId" HAVING count(*) > 1) d)
  UNION ALL SELECT 39, 'structure: DataType = entity', 0, (SELECT count(*) FROM live_a WHERE "DataType" = 'entity')
  UNION ALL SELECT 40, 'structure: DataType outside string/enum/number/boolean', 0, (SELECT count(*) FROM live_a WHERE "DataType" NOT IN ('string','enum','number','boolean'))
  UNION ALL SELECT 41, 'structure: TargetEntityId set', 0, (SELECT count(*) FROM live_a WHERE "TargetEntityId" IS NOT NULL)
  UNION ALL SELECT 42, 'structure: associations not Reference', 0, (SELECT count(*) FROM live_ea WHERE "Placement" IS DISTINCT FROM 'Reference')
  UNION ALL SELECT 43, 'structure: references with Relationship set', 0, (SELECT count(*) FROM live_ea WHERE "Relationship" IS NOT NULL)
  UNION ALL SELECT 63, 'count: reference associations with Array true (Registry multivalue; 321 false + 152 unknown are false)', 4929, (SELECT count(*) FROM live_ea WHERE "Array" = true)
  UNION ALL SELECT 44, 'structure: associations without a Name', 0, (SELECT count(*) FROM live_ea WHERE "Name" IS NULL)
  UNION ALL SELECT 45, 'structure: associations whose child is outside model 10', 0, (SELECT count(*) FROM live_ea a WHERE NOT EXISTS (SELECT 1 FROM live_e c WHERE c."Id" = a."ChildEntityId"))
  UNION ALL SELECT 46, 'structure: root entities with Array = Yes', 0, (SELECT count(*) FROM live_e WHERE "Array" = 'Yes')
  UNION ALL SELECT 47, 'structure: entities with Required set', 0, (SELECT count(*) FROM live_e WHERE "Required" IS NOT NULL)
  UNION ALL SELECT 48, 'structure: DataModel 10 live, Name CTDL', 1, (SELECT count(*) FROM "DataModels" WHERE "Id" = 10 AND "Name" = 'CTDL' AND "Deleted" IS NOT TRUE)
  UNION ALL SELECT 49, 'structure: attribute UniqueName not <Entity>.<Name>', 0, (SELECT count(*) FROM live_a a JOIN live_eaa x ON x."AttributeId" = a."Id" JOIN live_e e ON e."Id" = x."EntityId" WHERE a."UniqueName" <> e."UniqueName" || '.' || a."Name")
  UNION ALL SELECT 50, 'structure: duplicate attribute UniqueName', 0, (SELECT count(*) FROM (SELECT 1 FROM live_a GROUP BY "UniqueName" HAVING count(*) > 1) d)
  UNION ALL SELECT 51, 'structure: duplicate entity UniqueName', 0, (SELECT count(*) FROM (SELECT 1 FROM live_e GROUP BY "UniqueName" HAVING count(*) > 1) d)
  UNION ALL SELECT 52, 'structure: entity Name <> UniqueName', 0, (SELECT count(*) FROM live_e WHERE "Name" <> "UniqueName")
  UNION ALL SELECT 53, 'structure: EAA Name <> attribute Name', 0, (SELECT count(*) FROM live_eaa x JOIN live_a a ON a."Id" = x."AttributeId" WHERE x."Name" IS DISTINCT FROM a."Name")
  UNION ALL SELECT 54, 'structure: EAA Array disagrees with attribute Array (null attribute Array mirrors as false)', 0, (SELECT count(*) FROM live_eaa x JOIN live_a a ON a."Id" = x."AttributeId" WHERE x."Array" IS DISTINCT FROM (a."Array" = 'Yes' AND a."Array" IS NOT NULL))
  UNION ALL SELECT 62, 'structure: associations with a NULL Name or Array (the MDR reads NULL as not computed yet)', 0, (SELECT count(*) FROM live_ea WHERE "Name" IS NULL OR "Array" IS NULL) + (SELECT count(*) FROM live_eaa WHERE "Name" IS NULL OR "Array" IS NULL)
  UNION ALL SELECT 55, 'required: attributes Required = Yes', 242, (SELECT count(*) FROM live_a WHERE "Required" = 'Yes')
  UNION ALL SELECT 56, 'required: live entities with attributes but none Required (the two retained deprecated classes, never referenced)', 2,
      (SELECT count(*) FROM live_e e WHERE EXISTS (SELECT 1 FROM live_eaa x WHERE x."EntityId" = e."Id") AND NOT EXISTS (SELECT 1 FROM live_eaa x JOIN live_a a ON a."Id" = x."AttributeId" WHERE x."EntityId" = e."Id" AND a."Required" = 'Yes'))
  UNION ALL SELECT 57, 'deprecated: deprecated entities', 2, (SELECT count(*) FROM live_e WHERE "DeprecationDate" IS NOT NULL)
  UNION ALL SELECT 58, 'deprecated: deprecated attributes', 10, (SELECT count(*) FROM live_a WHERE "DeprecationDate" IS NOT NULL)
  UNION ALL SELECT 59, 'typing: enum attributes without a ValueSetId (96 scheme-not-in-file + 4 retained)', 100, (SELECT count(*) FROM live_a WHERE "DataType" = 'enum' AND "ValueSetId" IS NULL)
  UNION ALL SELECT 60, 'typing: non-enum attributes with a ValueSetId', 0, (SELECT count(*) FROM live_a WHERE "DataType" <> 'enum' AND "ValueSetId" IS NOT NULL)
  UNION ALL SELECT 61, 'temp functions dropped', 0, (SELECT count(*) FROM pg_proc WHERE proname LIKE 'ctdl_tmp_%')
)
SELECT ord, label, expected, actual, expected = actual AS ok FROM checks ORDER BY ord;
