# Learner Wallet Implementation Pattern Handout

One-page handout on using LIF to give wallet applications a holistic view of a learner's achievements across organizations.

## I. Use Case Description

- **Summary use case value prop** – Use LIF to provide wallet applications with holistic views of individual learners' academic achievements, credentials, employment experience, skills, and competencies from multiple organizations where learners have studied, worked, and served.
- **Value for learners** – LIF can supply data covering an expansive range of learners' achievements and experience, enabling learners to leverage the full functionality of their wallets to organize, curate, and share their accomplishments more easily in pursuit of educational and career aspirations.
- **Value for implementing organizations** – LIF can bring together learner data from across source systems and partner organizations to provide a wallet application with a holistic view of a learner's achievements and experience in a single format, simplifying wallet application integration, reducing time to value, and increasing wallet ROI for both learners and the organization.
- **Value for builders** – LIF can provide access to a broad range of learner data from implementing organizations in a single format, obviating the need to integrate with multiple source systems to retrieve the learner data required to populate the wallet. LIF also enables authorized retrieval of learner data from clients' partner organizations, expanding the pool of accessible data to enrich wallet contents.
- **Value to partners & networks** – LIF-populated wallet applications can increase the volume of applications for admissions or employment, reduce application frictions, and enhance recruitment efforts across networks and partnerships by making more comprehensive views of applicants and their credentials, skills, and experience readily available and easily shared.

## II. Use Case Data Flows and LIF's Role

![Data flow diagram for the learner wallet use case. A learner uses a learner wallet (LIF Clients, in the Application Provider) that connects to the LIF API. Inside the implementing organization, the LIF MCP Server, Query Planner, Composer, Identity Mapper, MDR, and LIF Cache sit alongside LIF Orchestration, which retrieves data from source systems and from a partner organization's LIF API Gateway.](../media/image_learnerWalletPattern_1.png)

![Wallet data source architecture. A wallet calls either a Wallet Client REST API or the LIF API (GraphQL) directly. The LIF API passes requests to the Query Planner, which uses the Identity Mapper and LIF Cache and reaches third-party orchestration. In that orchestration, a DAG with a read queue and adapters retrieves data from the source and passes it through the Translator. The MDR UI tool supports the LIF core components and the Translator.](../media/image_learnerWalletPattern_2.png)

## III. What LIF Adds to a Wallet Solution

- Today, wallet applications typically integrate directly with individual systems or rely on the learner to bring credentials and records into the wallet. This can require separate integrations for different source systems, organizations, and data formats, limiting the breadth of information available to the wallet and increasing implementation complexity.
- LIF does not replace the wallet application. Instead, LIF provides an interoperability layer between the wallet and the systems that hold learner information. LIF can retrieve data from multiple source systems, translate and compose that information into a consistent format, and make it available to the wallet through a standardized interface.
- Without LIF, wallet providers or implementing organizations may need to build and maintain multiple point-to-point integrations to access the range of academic, credential, employment, skills, and competency data needed to create a holistic learner record. With LIF, much of that integration, translation, and composition can be handled through shared infrastructure that can also support other applications and use cases.

## IV. What is in-scope vs. out-of-scope for LIF

- LIF is responsible for accessing, translating, composing, and delivering learner information to authorized applications. This includes identifying relevant data across connected source systems, translating data from different schemas and standards, composing information into a usable learner record, and providing that information to wallet applications through LIF interfaces.
- LIF assumes that wallet applications are running in a trusted and secure environment, and the wallet application is responsible for authentication and authorization. LIF does not currently function as the learner-facing identity, authentication, or consent-management system for the wallet.
- The wallet application remains responsible for the learner experience. Functions such as how learners authenticate, view and organize information, manage what they store or share, present credentials, and interact with other wallet features are outside the scope of LIF.
- LIF can support the movement of authorized learner data across organizations, but it does not establish the underlying trust agreements, governance policies, or permissions between those organizations. Implementing organizations and their partners remain responsible for determining what data may be accessed and shared.
