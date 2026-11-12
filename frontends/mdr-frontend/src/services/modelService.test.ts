import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./api", () => ({ default: { get: vi.fn() } }));

import api from "./api";
import type { DataModelWithDetailsWithTree, EntityTreeNode } from "../types";
import { generateJsonSchema, generateSampleRecords, getModelDetailsWithTree } from "./modelService";
import { buildDefaultAssignmentExpression } from "../utils/jsonataUtils";
import { validateAgainstSchema } from "../utils/schemaValidation";

// #1429: a node is a list where it sits by the generated schema's rule. A root is a list only when
// its own Array is 'Yes'; an embedded child follows its association's Array, or its own while the
// association's is unset; a reference is single.
const entity = (Id: number, Name: string, Array: string | null) => ({ Id, Name, UniqueName: Name, Array });
const attribute = (Id: number, Name: string, Required = "No") => ({ Id, Name, UniqueName: Name, DataType: "string", Required });
const child = (
  child: ReturnType<typeof entity>,
  AssociationArray: boolean | null,
  Placement: string | null = "Embedded"
) => ({ ...child, AssociationArray, Placement, Relationship: null });

const person = entity(1, "Person", "Yes");
const organization = entity(2, "Organization", null);
const identifier = entity(3, "Identifier", "No");
const contact = entity(4, "Contact", "Yes");
const course = entity(5, "Course", null);
const competency = entity(6, "Competency", "Yes");

const details = {
  DataModel: { Id: 99, Name: "test 1429 FE" },
  ValueSets: [],
  Transformations: [],
  DataModelConstraints: [],
  Entities: [
    {
      Entity: person,
      Attributes: [attribute(11, "firstName")],
      ParentEntities: [],
      // Identifier is a list under Person; Contact's association is unset, so its own Array decides.
      ChildEntities: [child(identifier, true), child(contact, null)],
    },
    {
      Entity: organization,
      Attributes: [attribute(12, "name")],
      ParentEntities: [],
      ChildEntities: [child(identifier, false)],
    },
    { Entity: identifier, Attributes: [attribute(13, "identifierValue")], ParentEntities: [person, organization], ChildEntities: [] },
    { Entity: contact, Attributes: [attribute(14, "email")], ParentEntities: [person], ChildEntities: [] },
    {
      Entity: course,
      Attributes: [attribute(15, "title")],
      ParentEntities: [],
      // A reference marked as a list is still a single object in the generated schema.
      ChildEntities: [child(competency, true, "Reference")],
    },
    // Only ever referenced, so the tree promotes it to a root.
    { Entity: competency, Attributes: [attribute(16, "code", "Yes")], ParentEntities: [course], ChildEntities: [] },
  ],
};

const findNode = (nodes: EntityTreeNode[], ...names: string[]): EntityTreeNode => {
  const [name, ...rest] = names;
  const node = nodes.find((candidate) => {
    const wrapper = candidate.Entity;
    return ("Entity" in wrapper ? wrapper.Entity : wrapper).Name === name;
  });
  if (!node) throw new Error(`no node ${name}`);
  return rest.length ? findNode(node.Children, ...rest) : node;
};

describe("entity cardinality (#1429)", () => {
  let model: DataModelWithDetailsWithTree;

  beforeEach(async () => {
    vi.mocked(api.get).mockResolvedValue({ data: structuredClone(details) });
    model = await getModelDetailsWithTree(99);
  });

  it("marks each node a list or single by the generated schema's rule", () => {
    const tree = model.EntityTree;
    expect(findNode(tree, "Person").IsArray).toBe(true);
    expect(findNode(tree, "Organization").IsArray).toBe(false); // a root with a NULL Array
    expect(findNode(tree, "Person", "Identifier").IsArray).toBe(true);
    expect(findNode(tree, "Organization", "Identifier").IsArray).toBe(false);
    expect(findNode(tree, "Person", "Contact").IsArray).toBe(true); // unset association falls back
    expect(findNode(tree, "Course", "Competency").IsArray).toBe(false); // a reference
    expect(findNode(tree, "Competency").IsArray).toBe(true); // the same entity as a root
  });

  it("takes a shared child's cardinality from each parent in the JSON Schema", () => {
    const roots = generateJsonSchema(model, model.EntityTree).properties;
    expect(roots.Person.type).toBe("array");
    expect(roots.Person.items.properties.Identifier.type).toBe("array");
    expect(roots.Person.items.properties.Contact.type).toBe("array");
    expect(roots.Organization.type).toBe("object");
    expect(roots.Organization.properties.Identifier.type).toBe("object");
    expect(roots.Course.properties.Competency.type).toBe("object");
    expect(roots.Competency.type).toBe("array");
  });

  it("generates sample records with the same shapes, valid against that schema", () => {
    const sample = generateSampleRecords(model, model.EntityTree, 2);
    expect(sample.Person).toHaveLength(2);
    expect(Array.isArray(sample.Person[0].Identifier)).toBe(true);
    expect(Array.isArray(sample.Organization)).toBe(false);
    expect(Array.isArray(sample.Organization.Identifier)).toBe(false);
    expect(Array.isArray(sample.Course.Competency)).toBe(false);

    const schema = generateJsonSchema(model, model.EntityTree);
    expect(validateAgainstSchema(sample, schema).issues).toEqual([]);
  });

  it("wraps a default JSONata assignment in [] only under the parent where the child is a list", () => {
    const schema = generateJsonSchema(model, model.EntityTree);
    const source = "Course.title";
    const underPerson = buildDefaultAssignmentExpression(schema, schema, source, "Person.Identifier.identifierValue");
    const underOrganization = buildDefaultAssignmentExpression(schema, schema, source, "Organization.Identifier.identifierValue");
    expect(underPerson).toContain('"Identifier": [{');
    expect(underOrganization).not.toContain("[{");
  });
});
