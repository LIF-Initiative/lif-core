# Dual Enrollment Implementation Pattern Handout

One-page handout on using LIF to create a transferable "universal transcript" for dual enrollment students.

## I. Use Case Description

- **Summary use case value prop** – Use LIF to create a transferable "universal transcript" that bridges the gap between K12 and postsecondary institutions for students in dual enrollment programs. This reduces administrative burden, ensures timely and accurate recognition of coursework, and empowers learners with a single, comprehensible record.
- **Value for learners** – Students receive one joint transcript that reflects both their high school and college coursework. This record reduces confusion, ensures credits are recognized, and makes it easier to apply for financial aid, admissions, and future opportunities.
- **Value for implementing organizations** – LIF streamlines dual enrollment data exchanges, reduces time-intensive manual processes, and eliminates silos across systems with different course codes or student IDs. Institutions can collaborate around a shared transcript format while maintaining their existing systems.
- **Value for builders** – LIF provides standardized access to student enrollment and transcript data from both K12 and higher ed without requiring unique integrations for each partner system. Builders can develop transcript services or advising tools more efficiently.
- **Value to partners & networks** – A unified transcript increases trust and transparency across partnerships, enabling smoother credit transfer, supporting admissions, and reducing administrative frictions that often slow down dual enrollment scaling.

## II. Use Case Data Flows and LIF's Role

**Today:** High school and college systems maintain separate records with no standard way to share data. Counselors manually reconcile coursework, which is time-intensive.

**With LIF:**

1. K12 and higher ed source systems feed learner data into the LIF translator and orchestrator.
2. LIF composes a joint record into a common model (mapped from Ed-Fi, Campus API, and transcript standards).
3. A "universal transcript" is generated and made available to students, institutions, and partners through trusted channels.

![Dual Transcript Architecture. A client calls a Dual Transcript Formatting API, which calls the LIF API (GraphQL) in the LIF core components. The LIF API passes requests to the Query Planner, which uses the Identity Mapper and LIF Cache and reaches third-party orchestration. In that orchestration, a DAG with a read queue and adapters retrieves data from source institutions and passes it through the Translator. The MDR UI tool supports the LIF core components and the Translator. The source institutions are a LIF implementation reached through a LIF-to-LIF adapter, a bespoke LIF connector deployed in the remote organization in lieu of LIF, a standards-based API service, and a bespoke-format API service, each with a non-LIF backend. A note says multiple adapters support the LIF format and other standards.](../media/image_dualEnrollmentPattern_1.png)

## III. LIF vs. another solution

- Without LIF: Dual enrollment partnerships typically rely on institution-specific data exchanges, custom integrations, and manual processes to reconcile student identities, course information, and academic records across K-12 and postsecondary systems. While existing standards and integration solutions can support these exchanges, differences in systems, data formats, and institutional practices often require additional mapping and development for each partnership.
- With LIF: LIF provides a reusable interoperability layer that helps institutions retrieve, translate, and compose learner information from multiple systems into a consistent format. This reduces the need for custom point-to-point integrations, supports more consistent data exchange, and makes it easier to expand dual enrollment partnerships without replacing existing institutional systems.
- What makes LIF different: Rather than introducing another transcript system or requiring institutions to adopt a single vendor's platform, LIF works alongside existing systems and standards. Its shared data model, translation capabilities, and standardized interfaces help institutions make use of the information they already maintain while reducing the technical complexity of exchanging it.

## IV. What is in-scope vs. out-of-scope for LIF

- Data access and interoperability: LIF supports the retrieval, translation, and composition of learner information across connected K-12 and postsecondary systems. This includes mapping data from different schemas and standards into a common representation and making it available to authorized applications through standardized interfaces.
- Identity mapping: LIF supports mapping learner identifiers across connected systems to help associate records belonging to the same individual. However, institutions remain responsible for establishing reliable identity-matching processes and resolving ambiguous or conflicting identities.
- Authentication, authorization, and security: LIF assumes that participating institutions and applications operate within a trusted and secure environment. Authentication, authorization, and enforcement of data access permissions remain the responsibility of implementing organizations.
- Data governance and sharing agreements: LIF provides technical infrastructure to support data exchange but does not establish data-sharing agreements, determine which organizations are authorized to access information, or replace institutional governance and privacy requirements.
- Academic decisions and transcript issuance: LIF can help assemble and exchange academic information, but institutions remain responsible for maintaining authoritative academic records, issuing official transcripts, determining course equivalencies, and awarding or recognizing academic credit.
