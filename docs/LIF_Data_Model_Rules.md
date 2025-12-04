# LIF Data Model Rules

## Table of Contents

[Context and Intentions for LIF Data Model Rules](#context-and-intentions-for-lif-data-model-rules)

[No Loss Capture](#no-loss-capture)

[Attribute Data Type](#attribute-data-type)

[Naming Styles](#naming-styles)

[Object Effective Date](#object-effective-date)

[Object End Date](#object-end-date)

[Data Exclusion or Deletion](#data-exclusion-or-deletion)

[Required Fields](#required-fields)

[Data Source Organization](#data-source-organization)

[Arrays](#arrays)

[Entity - Entity Relationship](#entity---entity-relationship)

[Entity - Entity Reference](#entity---entity-reference)

[Descriptions](#descriptions)

[Common](#common)

[Queryable & Modifiable](#queryable--modifiable)

[Organization Specific LIF Data Model](#organization-specific-lif-data-model)

[Enumerations](#enumerations)

[Authoritative System(s)](#authoritative-systems)


These rules are intended to maintain the integrity of the data model; however, there may be a need in the future for modifications to these rules as new use cases are discovered.

## Context and Intentions for LIF Data Model Rules

### No Loss Capture
The LIF Data Model aims to include all data from every data source. When data is updated, the previous data in LIF Cache remains unchanged and is kept as a historical artifact. The new data is added with an effective date to indicate the start time of the latest data and the end time of the previous data.

**Reasoning:** The LIF Data Model gathers data from various sources, consolidating all information related to a person into a single LIF record.

## LIF Data Model Rules

### Attribute Data Type
The LIF Data Model utilizes a primitive JSON data type. Primitive data types include strings, numbers, booleans, and nulls. Strings are mainly used to provide flexibility in data.

**Reasoning:** The primitive JSON data type was selected for LIF because of the “no loss” principle in data acceptance. The team worried that using a more rigid data type might prevent data from fitting correctly. For instance, when a date is expected, it may include the full date with month, day, and year, or only the month and year, or just the year. By choosing a primitive JSON data type with most data stored as strings, we can ensure that, regardless of how the data is stored in the source system, it will be accurately captured in the LIF model.

### Naming Styles
- **Entities:** Upper CamelCase, first letter capitalized.
- **Properties:** standard CamelCase.
- **Enums:** Upper CamelCase, first letter capitalized.

**Reasoning:** The different naming styles were chosen to make the text not only easy to read, but also to help quickly identify whether you're looking at an entity or a property, since entities use UpperCamelCase and properties use standard camelCase.

### Object Effective Date 
Object effective dates are set when the object is created. The date indicates not only when the date was added but also when any previous objects in the array became deprecated. The Object Effective Date is stored in a field named `dateEffective` in ISO 8601 standard format: `YYYY-MM-DD`.

**Reasoning:** Object effective dates inform the system and possibly users when data is valid. Not all objects will have an effective date. For example, a birth date would not have an effective date because it does not change. In contrast, a person’s primary address would have an effective date, as they may have lived at different addresses, but only their current address is considered their primary address.

### Object End Date
Objects that may expire or become invalid should include a `dateEnd` field in ISO 8601 standard format: `YYYY-MM-DD`. The data model should not use any other field names for this purpose.

**Reasoning:** The LIF data model should include longitudinal data to track how a learner's information changes over time. For example, a learner might have credentials that expire. Therefore, having a common field to indicate when data becomes invalid is essential. It is important to use a single field name and format to represent this concept, ensuring the data model is clear, consistent, easy to understand, and simple to map to other data models.

### Data Exclusion or Deletion
Every entity must have a `deletedDate` field to indicate when the data has been deleted. Every entity must also include a `deletedStatus` string field that specifies the reason for deletion, such as: `"Missing at will"`, `"Not applicable"`, `"Incorrect"`, or `"Changed over time"`.

**Reasoning:** To follow our principle of No Loss Capture, the data model is designed to retain deleted data and offer additional context about why it was deleted.

### Required Fields
There are two types of required fields:

1. The first type of required field is for creating a LIF record. A `Person` object is required for all LIF records, and as an example, `lastName` is a required field to create a `Person` object.

2. The second type of required field is when creating new objects. An example of the second type of required field is when adding a new address; the `effectiveDate` is a required field. Each object will have its own set of required fields and may require more than one field to be valid.

**Reasoning:** A minimum amount of data is required to create a new LIF record. Since all LIF records are oriented around a person, the Person object is required. Similarly, when adding other objects to the record, a minimum amount of data must be captured to make the object valid. In the example above, when adding a new address, an `effectiveDate` is required to convey when the address became effective.

### Data Source Organization
Every LIF Entity must include fields that help identify the source system of the data. These fields are `identifier`, `informationSourceId`, `informationSourceOrganization`, and optionally, `informationSourceSystem`.

- The `identifier` field is to provide a unique identifier for that data. This field, along with `informationSourceId` and `informationSourceOrganization`, allows each block of data to be uniquely identified.
- The `informationSourceId` field is an identifier used by the LIF software components to distinguish the source system of the data.  
- The `informationSourceOrganization` field should specify the name of the organization that owns the source system.  
- If an organization provides data from multiple source systems, the `informationSourceSystem` field can be used to specify which system the data originates from (e.g., “Canvas LMS”, “Ellucian SIS”).

**Reasoning:** When a LIF record is transferred to downstream systems, it is important to know that certain data originated from different source systems via the `informationSourceId`. Additionally, these downstream systems may have use cases that require a human-readable name for the data source, including the organization name and source system name.

### Arrays
- Every LIF Entity must be a JSON array of objects.
- Within an Entity, any Property or Attribute may be a JSON array only if it represents a natural one-to-many relationship that does not justify the creation of a new Entity.

Examples:
- `Assessment.languages` is an array of language codes indicating all supported languages for the assessment.
- `Assessment.deliveryType` is an array of delivery mode descriptors indicating all applicable delivery formats.

**Reasoning:** This rule balances expressive structure with practical simplicity. Arrays of objects are required for LIF Entities to enable rich, extensible modeling. At the same time, arrays of primitives are allowed for Properties only when there is a clear one-to-many relationship that doesn’t justify creating a separate Entity.

### Entity - Entity Relationship
The LIF data model contains a set of relationships used to associate an entity to another entity. The relationship type, followed by "Ref", is prepended to the entity name when it is referenced within another entity. For example, if the relationship type is "offeredBy" and the referenced entity is "Organization", then the name of the field for this reference is "offeredByRefOrganization". For another example, if there is no relationship type and the referenced entity is "Course", then the name of the field for this reference is "RefCourse".

**List of relationships:**
- **offeredBy** – Organization or entity providing a course, program, training, or credential.  
- **accreditedBy** – Organization accrediting or recognizing standards.  
- **issuedBy** – Authority that grants/awards credential.  
- **approvedBy** – Entity or individual who reviewed/approved.  
- **assertedBy** – Entity declaring a skill or competency.  
- **basis** – Foundational data or rationale.  
- **demonstrates** – Connects entity to competencies.  
- **aligned** – Correspondence to framework or standard.  
- **entailed** – Requirement implied within another.  
- **instanceOf** – Links record to general class/type.  
- **requires** – Specifies prerequisites.  
- **withdrawalProcess** – Describes removal process.

**Reasoning:** These prefixes provide consistency and avoid duplication.

### Entity - Entity Reference
- The LIF record is a JSON object of entities.
- Each entity is an array of JSON objects.
- The root of the LIF record must contain the Person entity.
- Person entities hold data directly tied to individuals.
- Non-person-related entities (e.g., `Organization`) are defined at the root level.
- Each referenced entity should contain only the required fields of the entity.

**Example JSON:**

```
json {   "Person": [
    {
      "Identifier": [
        { "identifier": "67890" }
      ],
      "CredentialAward": [
        {
          "uri": "https://www.examplecredentials.com/person123",
          "issuerOrganization": {
            "identificationSystem": "Local Education Agency",
            "name": "Example University",
            "organizationType": ["Education Institution"],
            "informationSourceId": "123456789"
          }
        }
      ]
    }   ],   "Organization": [
    {
      "description": "A private research university.",
      "identificationSystem": "Local Education Agency",
      "imageUrl": "https://www.university.edu/logo.png",
      "informationSourceId": "123456789",
      "name": "Example University",
      "organizationType": ["Education Institution"],
      "shortName": "Univ of Example"
    }   ] }
```

### Descriptions 
All entities, attributes, and values should have descriptions explaining what data is captured. Each relationship should also have a description.

### Common The LIF data model includes a limited set of common elements:
- LegalCode
- Accreditation
- Identifier
- Contact   - Address   - Email   - Telephone

### Queryable & Modifiable
- `queryable` indicates if data can be filtered via GraphQL. Default is `false`.
- `modifiable` indicates if data can be edited. Default is `false`.

### Organization Specific LIF Data Model
- One org-specific model per MDR instance.  
- Can extend base model with enums/entities.  
- Maintains consistency.

### Enumerations 
**Strict Enumeration Fields include:**
- Competency.language
- AddressState
- LifEntities
- TribalNationName
- Assessment.contentStandardStatus
- CompetencyFramework.validEndDateStatus
- CompetencyFramework.validStartDateStatus
- MilitaryLearningExperience.dischargeDateStatus
- Position.compensationBaseSalaryStatus
- CompensationTotalSalaryStatus
- ContractDaysOfServicePerYearStatus
- ContractLengthStatus

**Extensible Enumeration Fields include:**
- Gender
- Sex
- AssessmentLevel
- PublicationStatus
- CourseApplicableEducationLevel
- Credential.idType
- HighestLevelEducation
- MilitaryLearningExperience.branch
- NormalTimeCompletionUnits

### Authoritative System(s) 
Authoritative system(s) are not defined in the model. Each organization must determine which systems are the authoritative system(s). 
