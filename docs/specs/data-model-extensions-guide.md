# LIF Data Model: Future Changes & Extensions Guide

How to propose changes to the Base LIF data model, when to build an extension instead, and the rules extensions must follow.

## Future Changes

When proposing changes to the LIF Data Model, first verify that the requested Entities, Attributes, Values, or Value Sets do not already exist in the Base LIF model or in any existing extensions. The MDR should be used to confirm whether the element already exists or is defined in another model for potential reuse.

If the item does not exist, determine whether it should be proposed for inclusion in the Base LIF Data Model or added as an extension. Base model additions should be reserved for data elements that are broadly needed across many organizations, improve interoperability, and align with LIF's mission of representing a learner's full educational and workforce journey. Specialized or domain-specific needs should be addressed through extensions.

All proposed additions must comply with existing LIF Data Model Rules, including naming conventions, effective and end date conventions, deletion semantics, information source fields, required fields, and the use of common elements. Proposed enumerations must follow the strict or extensible enumeration rules defined for the model. See the [LIF data model rules](data-model-rules.md).

If the proposed change is believed to warrant inclusion in the Base LIF Data Model, a community discussion must be initiated. Proposals should include use cases, justification, schema impact analysis, and alignment with existing standards. The community will review and refine the proposal before submission to the Steward for approval. Approved changes will be versioned and documented to ensure clarity and backward compatibility.

### Suggested Steps for Evaluating a Proposed Change

1. **Check existence in Base LIF model.** Use the MDR to confirm whether the Entity/Attribute/Value/ValueSet already exists in the base LIF data model.
2. **Check for existing extensions.** Verify whether another organization or partner model already defines the element.
3. **Assess the scope of need.** Determine whether the proposed data is relevant to:
    - most/all institutions (base LIF model candidate), or
    - a subset, domain-specific, or organization-specific (extension candidate).
4. **Evaluate semantic alignment.** Ensure the new element fits the conceptual boundaries of its target Entity and does not replicate existing semantics.
5. **Verify LIF data model rule compliance.** Review the [LIF data model rules](data-model-rules.md) to determine compliance.
6. **Confirm effects on interoperability.** Adding fields to the base model affects all organizations; additions must not compromise transportability or introduce redundancy.
7. **Community review and steward approval.** Only items meeting broad need and clear justification should proceed to Base LIF review.

## Extension vs Base LIF Data Model

Extensions and the Base LIF Data Model serve different purposes in the LIF ecosystem, and understanding this distinction ensures that the model remains interoperable, scalable, and adaptable to diverse organizational needs.

The Base LIF Data Model defines the shared, common structure used across all organizations implementing LIF. Any element added to the base model becomes part of every organization's data model by default. If an organization does not need that element, they must explicitly exclude it from their organizational model. Because base-model changes immediately affect the entire community, only data elements that meet broad, cross-institutional needs should be added to the base. These additions must support interoperability, align with LIF's mission, and adhere to all model rules.

Extensions allow organizations or domains to introduce additional Entities, Attributes, Value Sets, or Values without modifying the shared base. Extensions are layered on top of the Base LIF model and appear only in the organization data models that choose to adopt them. This avoids forcing specialized or niche requirements onto every institution and prevents unnecessary complexity in the base model. Extensions follow all LIF Data Model Rules, but provide organizations with the freedom to innovate, capture domain-specific data, or model optional use cases without impacting others.

A more simplified explanation of the difference is:

- Base additions expand the universal vocabulary of LIF for everyone.
- Extensions expand only the vocabulary of those who need them.

With the wide impact of base changes, any proposal to add items directly to the Base LIF Data Model must be brought to the community for discussion. Proposed elements should include justification, use cases, and expected benefits. After community vetting, the proposal can be submitted to the LIF Steward for final approval. Extensions, meanwhile, can be developed and implemented at the organization without requiring changes to the shared model.

## Guidelines for Creating a LIF Data Model Extension

When designing an extension to the LIF Data Model, organizations must ensure that new elements are compatible with the Base LIF model and do not compromise interoperability, clarity, or future scalability. The following considerations and rules apply to all extensions.

### 1. Follow all LIF Data Model Rules

All entities, attributes, naming conventions, effective date rules, deletion semantics, information source fields, and relationship types must comply with the LIF Data Model Rules. This ensures that extensions behave consistently with the rest of the model and are easy to integrate into the MDR, GraphQL API, and downstream systems. Below are examples of what must be followed; always refer to the LIF Data Model rules.

Designers must ensure:

- Entities use UpperCamelCase
- Attributes and value sets use camelCase
- Values/enums use UpperCamelCase
- dateEffective, dateEnd, deletedDate, and deletedStatus follow standard fields and ISO formats
- Common elements (Identifier, Contact, LegalCode, etc.) are reused where appropriate
- Arrays and cardinality follow the LIF rules for structure

### 2. Do not redefine or override the meaning of any base element

Extensions should not:

- Repurpose a base attribute or entity to carry a different meaning
- Introduce a conflicting definition for an existing value or value set
- Change required fields or semantics for base entities
- Narrow or broaden the meaning of a base element in a way that affects interoperability
- Introduce alternative relationship names or formats already defined in the LIF rules

Extensions exist to supplement the base model, not modify it. If the meaning of a base element needs to change, this must go through the Base LIF change process and community vetting.

### 3. Add new entities, attributes, values, and value sets

Extensions can introduce new data elements to meet organizational or domain-specific needs. This includes:

- New entities that represent additional categories of data
- New attributes that enrich existing entities
- New enumerated values
- Entirely new value sets (when no existing set captures the needed semantics)

However, additions should maintain conceptual alignment with the Base LIF model and avoid unnecessary duplication of existing concepts.

Designers should avoid:

- Adding multiple entities that express the same idea
- Creating attributes that compete with existing base ones ("addressStreet2", "altIdentifier", etc.)
- Creating deeply nested structures that break LIF's readability and interoperability
- Introducing new patterns that contradict LIF norms (for example, inventing new date fields instead of using dateEffective/dateEnd)

The goal is to extend the model without fragmenting it.

### 4. Enumerations must use the "Ext-" prefix

Attributes with extensible enumeration rules require values not present in the base list to be prefixed with "Ext-". This supports validation and ensures downstream systems can distinguish between standard, community-approved values and local extensions.

Example: if the base enumeration includes:

```json
["MissingAtWill", "NotApplicable"]
```

And an organization needs a custom value:

```text
"Ext-PendingApproval"
```

This ensures consistency and preserves compatibility with validators and consuming applications.

### 5. Do not duplicate elements already available in the Base model or other extensions

Before adding new attributes or entities, organizations should check:

- The Base LIF Data Model
- Partner or community extensions
- MDR inheritance paths

If an existing element captures the meaning, reuse it rather than recreate it. Duplication leads to mapping inconsistency and reduces portability.

### 6. Maintain interoperability wherever possible

Although extensions support local needs, they should still be designed with cross-system compatibility in mind.

Extension designers should consider:

- Whether other organizations may someday adopt this extension
- Whether existing standards (CEDS, CTDL, Open Badges, etc.) offer patterns worth aligning with
- Whether the structure supports long-term maintenance and change
- Whether data from this extension will travel meaningfully through LIF pipelines

A good extension increases clarity and expressiveness without isolating the data.

### 7. Define clear descriptions for every element

Per the LIF Rules, all entities, attributes, relationships, value sets, and values must include descriptions that explain:

- What the element represents
- Why it exists
- How it should be used
- Any constraints or semantic expectations

This is critical for MDR usability and for future implementers who inherit or interact with your model.

### 8. Avoid introducing new authoritative-system assumptions

Extensions should not encode organizational logic that belongs in:

- Pre-processors
- Post-processors
- Business rules
- Access policies

The extension should capture data, not process. Authoritative system behavior is handled outside the data model.

### 9. Consider versioning and long-term maintenance

Organizations should maintain:

- A semantic version for the extension
- A changelog
- Clear documentation for new fields

This helps downstream partners and tools anticipate changes.

### 10. Validate through the MDR before deployment

Extensions must be tested for:

- Schema validity
- Proper inheritance
- Conformance to naming and structural rules
- Compatibility with sample LIF records
- Validation behavior for new enums

This ensures smooth integration into the technical stack.
