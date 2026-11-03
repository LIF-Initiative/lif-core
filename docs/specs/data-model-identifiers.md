# LIF Data Model: Identifiers

Definitions, requirements, and usage recommendations for the identifier and information source fields on LIF entities.

## informationSourceId

**Required:** Yes

**Definition:** An identifier key that represents a combination of informationSourceOrganization and informationSourceSystem from which this entity data came. Typically, this value is configured in the orchestrator and applied to the LIF record as it is generated. This could be a human or machine-readable value.

## informationSourceOrganization

**Required:** Yes

**Definition:** The organization from which this entity data came, such as a school, college, employer, agency, or vendor. Typically, this value is configured in the orchestrator and applied to the LIF record as it is generated. This could be the organization's name or another preferred way to indicate the organization. This value may be visible to students or instructors via external applications or an LLM advisor, so it should be something easily identifiable. This field should help users identify which system to refer to if they have questions about the data associated with this field.

## informationSourceSystem

**Required:** No

**Definition:** The specific information system, application, or pipeline from which this entity data came. Examples include SIS, LMS, HR Systems, CRMs, and data warehouses. Typically, this value is configured in the orchestrator and applied to the LIF record as it is generated. This value may be visible to students, instructors, or staff via external applications or an LLM advisor, so it should be something easily identifiable. This field should help users identify which system to refer to if they have questions about the data associated with this field.

## identifier

**Required:** Yes

**Definition:** The primary key identifier for this entity data in the LIF data model. This value should uniquely identify this particular instance of the entity. The identifier can be created based on external identifiers, a newly created identifier unique to LIF, or a composite of other attributes related to the entity.

**Use recommendations:** Personal or sensitive information should not be used as part of the identifier. If external sources are used to create the identifier, consent should be considered.
