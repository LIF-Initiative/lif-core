# LIF Data Model Guide (Draft)

Guide to the Base LIF data model and how to develop an organization-specific data model, with technical notes and FAQs.

## Purpose

The purpose of this document is to provide general information on the Base LIF Data model and how to develop an organization-specific data model.

## Base LIF Data Model

### What is the Base LIF Data Model

The LIF Data Model was built to provide a clear, structured representation of a person and their associated data. The LIF Data Model defines how learner data is organized within the LIF framework. It defines entities, or categories, of data pertaining to a learner as well as how these data points relate to each other. The LIF Data Model serves as the basis for each implementing organization's LIF-based data model, improving consistency when sharing data across organizations.

### How the Base LIF Data Model was developed

The current fragmentation of information across various systems makes it challenging to have a complete view of a learner's experiences and achievements, which can lead to even more challenges for underrepresented learners. This model aims to connect the dots across education and workforce systems. The initiative involves stakeholders from technology, education, employment, and data standards communities working together to integrate and protect learner information.

LIF was developed to serve marginalized and underrepresented learners, allowing for the capture and transportability of their data. The purpose of the LIF data model is to provide a detailed, inclusive framework that can support marginalized learners by integrating data from diverse source systems from their educational and employment journeys. The model aims to respect ethical data use, protect individual rights, and promote equitable outcomes. The LIF model includes a large number of data elements to create a comprehensive picture of a person's learning, education, earning, and work journey, especially targeting the new majority learners and those from marginalized communities.

A crosswalk analysis was performed to understand the semantics of learner information across roughly a dozen common data standards. This helped in creating a normative data model and establishing translation instructions for converting data from other standards. The analysis was performed across 10 different domain categories:

- Assessment
- Competency
- Consent
- Context
- Course
- Credential
- Employment
- Organization
- Person
- Program

The LIF data model is substantially influenced by the Common Education Data Standards (CEDS) and the Learning and Employment Records Resource Standard (LER-RS). Its primary focus is capturing a learner's educational and employment data in a structured, comprehensive manner.

### Data Models referenced when developing the Base LIF Data Model

- CEDS
- Open Badges v2
- CTDL
- CLR v2 / Open Badges v3
- CLR v1
- CASE
- OB2
- 1EdTech
- HR Open
- ELM
- Ed-Fi

### How is the LIF Data Model different from other data models?

#### Use and Access Considerations

The foundational premise of LIF is that it is intended to serve marginalized and underrepresented learners. Building a comprehensive data model that includes multidimensional person details will equip implementing organizations with the necessary information to provide services to persons in underrepresented, marginalized groups. A core principle of use considerations is the fair and just use of data that respects ethical principles, protects individual rights, and promotes equitable outcomes.

A narrative document was developed that outlines the Person domain and offers additional resources, alongside the existing recommendations. This document aims to provide users of the LIF model with insights and considerations for effective implementation.

During the review of each element within the Person domain, several key questions were considered, including an examination of each element's description across various standards and definitions. Each element was assessed for its relevance in relation to LIF goals and provided with necessary explanations.

Recommendations for what to include have been provided. In many cases, consent should be obtained on an item-by-item basis. To address this, certain data elements are optional for organizations using these items. This allows users to include or exclude elements at their discretion, based on the appropriateness for their specific use case.

#### Base LIF Data Model Alignment to Other Standards

**CEDS**
The LIF data model differs from CEDs because, while CEDS includes learner data, it is not learner-centered like LIF. CEDS also contains significant data about faculty at institutions ranging from early childhood care to postsecondary education, whereas LIF does not focus on faculty data.

**LER-RS**
The LIF data model is different from LER-RS in that it contains more detailed information about the assessments, courses, and programs that the learner participated in, as well as the competency frameworks that may have been used to develop the content of the assessments, courses, and programs.

**OpenBadges/CLR**
The LIF data model is different from OpenBadges/CLR in that it contains much more personal information about the learner, more information about the assessments, courses, programs, and employment that the learner participated in, as well as the competency frameworks to which those may have been aligned.

### LIF Data Model Rules

LIF has defined rules that are used in the Base LIF data model and for creating new elements or associating elements in an Organization LIF Data Model. Please refer to the [LIF Data Model Rules](../specs/data-model-rules.md).

## Technical Information

### Introduction

The LIF data model was designed to address the challenges posed by numerous disparate data standards, which made it difficult to combine and transfer learner data effectively. It accomplishes this in two main ways. First, all entities within the LIF data model can have zero to many instances, enabling a learner to have multiple records of the same category of data sourced from different providers all in one location. Second, the LIF data model is highly flexible, allowing it to easily adapt to various needs and requirements.

The primary purpose of the LIF is to transport data, typically between organizations. Therefore, the LIF data model is formatted in JSON, as this is the standard format used for data transportation via GraphQL and REST APIs.

These entities are at the top-most level of the JSON structure: Assessment, CompetencyFramework, Course, Credential, Organization, Position, Program, and Person. This ensures that all data not directly related to Person is considered external to the Person entity, which still focuses on the individual's experiences with each of these separate entities. By having all data not directly related to Person external to the Person entity, the LIF record is able to efficiently handle entities that are repeatedly referenced in the Person entity, such as several course learning experiences from the same organization.

It was decided early on that a LIF record should only pertain to exactly 1 learner at a time.

The LIF data model is extremely flexible. It is possible to extend the model by increasing its cardinality, removing required fields, expanding or removing enum value sets, and adding new entities and properties when needed.

Below is a high-level visualization of the Base LIF data model to show how Entities are connected.

![The LIF Normative Model. Person (with Name, Birth, Sex / Gender, Demographic, Language, Contact, and Relationship) connects to Identifier, Consent, Learning Experience (Assessment, Course, Employment, Military, Program), Credential Award, and Proficiency Result. Organization connects to Identifier and Learning Experience. Learning Opportunity (Assessment, Course, Employment, Program) connects to Learning Experience and to Competency (Spec.). Credential Award connects to Credential (Spec.), and Proficiency Result connects to Competency (Spec.).](../media/image_dataModelGuide_1.png)

The screenshot below of lif-sample.json shows the root-level entities in the Base LIF data model, along with the sub-entities of the Person entity.

![Screenshot of lif-sample.json in a code editor, collapsed to show the root-level entities (Assessment, CompetencyFramework, Course, Credential, Organization, Position, Program, and Person) and the sub-entities of Person, such as AssessmentLearningExperience, Birth, Consent, Contact, CourseLearningExperience, CredentialAward, and Name.](../media/image_dataModelGuide_2.png)

## Code & Libraries

### lif-data-model Repository

The [lif-data-model](https://github.com/LIF-Initiative/lif-data-model) GitHub repository is accessible to the public. The OpenAPI schema for the LIF data model is in the lif.json file. The MDR generates OpenAPI schema files that show what a sample LIF record looks like.

The MDR (MetaData Repository) is included in the [lif-core GitHub repository](https://github.com/LIF-Initiative/lif-core).

### Accessing the Data Model

Using the MDR (MetaData Repository), the Base LIF Data model can be accessed, viewed, and exported in OpenAPI JSON schema format. When the data model is instantiated, it should be in JSON format because it is intended for data transfer. It can be converted to a tabular format for relational database use. The MDR includes a UI and an API for accessing and manipulating the base LIF, organization's LIF, source system, and partner LIF data models.

## FAQs

### How do you extend the data model?

See the [LIF Data Model Extensions Guide](../specs/data-model-extensions-guide.md) for the rules an extension must follow, and [Add New Elements in the MDR Getting Started guide](../external/mdr-getting-started.md#step-4-add-new-elements-optional) for how to add entities and attributes in the MDR.

### What elements make up the LIF data model?

The LIF data model consists of Entities, Attributes, Value Sets, and Values.

### What is an Entity?

A LIF Entity is a grouping of related data that always travels together. Technically, it is a schema for a JSON object. For example, one of the LIF Entities is Address and this contains all of the details of a person or organization's physical address.

### What is an Attribute?

A LIF Attribute is a single unit of data. It is a field within the JSON schema. For example, one of the LIF Attributes is addressStreet, which belongs in the Address Entity.

### What are Value Sets and Values?

A Value Set is a collection of possible Values that must be used for the data of an Attribute to increase interoperability. For example, addressState has a Value Set that indicates that all states should be written in full upper camel case format (e.g., "NorthCarolina") as opposed to an abbreviated format like "NC" or any other format, so that all LIF records represent states in the same way.

### How are common elements reused within the LIF schema?

Some elements in the LIF data model schema are reused within multiple entities. There are two primary examples of these: Identifier and Contact, which can both apply to either Person or Organization. These elements are defined under a Common Entity in the MDR but are only instantiated as children of other Entities in the data model.

### What does Proficiency mean in the context of the LIF Data Model?

The ProficiencyResult entity is the place to store final grades for any Learning Experience. It can also be used as the entity for holding a learner's skills. Proficiency is considered synonymous with "skill," and if the entity is extended, it can include a grade or score for a learning experience.

### What are informationSourceId, informationSourceOrganization, and informationSourceSystem? How should they work in the LIF Data Model?

The purpose of informationSourceId, informationSourceOrganization, and optionally informationSourceSystem is to provide a location in the LIF record where the data source can be identified. This allows LIF records to include data from various sources, making it possible to differentiate between them. These fields are attached to each LIF entity. The value for informationSourceId is determined by the implementer and configured within the LIF technical stack. informationSourceId is a required field and should indicate the data source. informationSourceOrganization is also required and should specify the name of the organization that provided the data. informationSourceSystem is an optional field that stores the name of the source system from which the data originates. Collectively, these fields are used to precisely identify the system within an organization from which the data comes.

### Are there any known gaps in the Data Model?

The LIF Data Model was primarily developed with a higher education influence. The LIF Data Model includes limited coverage for the following domains, however, the model can be extended to include them:

- Early Learning
- K12
- Facilities
- faculty/staff
- parents/guardians

### How are common pieces of data referenced in the model?

Data that is more than one layer deep in the LIF JSON and referenced for a second time should be implemented as a "reference". A "reference" in LIF consists of either the required fields or the data that is available (if there is no data for the required fields).

As an example, the required fields in AssessmentLearningExperience are type, identifier, and informationSourceId, but this source system did not have a value for type, so we will treat just identifier and informationSourceId as the required fields when referencing this assessment from the Person's CourseLearningExperience:

```json
{
    "Person": [
        {
            "AssessmentLearningExperience": [
                {
                    "type": "string",
                    "identifier": "Exam2024-104",
                    "informationSourceId": "123456789",
                    "informationSourceOrganization": "StateU SIS",
                    "completionStatus": "Completed",
                    "deliveryDeviceDetails": "Online",
                    "endDate": "2024-05-20T16:00:00Z",
                    "experienceLocation": "University Testing Center",
                    "gradeStatus": "pass",
                    "offeredBy": "Department of Computer Science",
                    "reasonNotCompleting": "Other",
                    "resultDataType": "Percentile",
                    "scoreType": "Final Exam",
                    "scoreValue": "85",
                    "startDate": "2024-05-20T09:00:00Z",
                    "timeAssessed": "7 hours"
                }
            ],
            "CourseLearningExperience": [
                {
                    "RefAssessmentLearningExperience": {
                        "identifier": "Exam2024-104",
                        "informationSourceId": "123456789"
                    },
                    "type": "array",
                    "identifier": "CS101-2024",
                    "informationSourceId": "123456789",
                    "informationSourceOrganization": "StateU SIS",
                    "courseSectionID": ["CS101-Spring2024", "CS102-Fall2024"],
                    "courseSectionNumber": 104,
                    "courseTotal": 5,
                    "currentlyAttendingIndicator": "Yes",
                    "department": "Computer Science",
                    "endDate": "2024-12-15",
                    "enrollmentStatusType": "Completed",
                    "exitDate": "2024-12-15",
                    "experienceGrade": "A",
                    "experienceNumericalGrade": 93.5,
                    "goodStandingIndicator": true,
                    "institution": "Tech University",
                    "narrativeExplanationGrade": "Exceeded all expectations.",
                    "ownedBy": "Department of Natural Science",
                    "personId": "123e4567-e89b-12d3-a456-426614174000",
                    "singleSexClassStatus": ["NotSingleSex"],
                    "startDate": "2024-08-01"
                }
            ]
        }
    ]
}
```

### How do we ensure that 'Missing at will' and 'Not applicable' can be labeled as values for fields?

For use considerations, many fields can indicate "Missing at will" or "Not applicable" as possible values. This is accommodated in string fields and enumerated fields.

## Designing an Organization LIF Data Model

The Base LIF Data model is a template data model and is intended to be customized by Organizations by creating their own data model. Using the MDR (MetaData Repository), each organization creates a LIF Data Model that can include or exclude existing elements from the Base LIF Data model, as well as create new entities and attributes to customize the data model for the organization's needs.
