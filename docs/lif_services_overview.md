<!-- markdownlint-disable MD013 -->
# LIF Microservices Overview

## Understanding LIF as Building Blocks

LIF (Learner Information Framework) provides infrastructure components for building custom learner data workflows - not a one-size-fits-all product. Think of these micro-services as building blocks that can be composed to create tailored solutions for aggregating, transforming, and accessing learner information across multiple systems and institutions.

Each service addresses a specific responsibility in the learner data ecosystem. Organizations typically use a subset of these services based on their specific integration and analytics needs.

---

## Core Data Services

These services handle the fundamental data operations: querying, transformation, identity resolution, and metadata management.

### 🔍 LIF GraphQL API

**WHEN YOU NEED TO...**  
Provide a standardized query interface for accessing learner data across multiple source systems using a flexible, modern API.

**THIS SERVICE...**  
Exposes learner data through a GraphQL interface, routing queries to the Query Planner to fetch data in the LIF data model format.

**USE CASES:**

- Building dashboards that pull learner data from multiple systems
- Creating APIs for institutional data portals
- Developing custom analytics applications that need learner information
- Integrating learner data into third-party applications

**WORKS WITH:** Query Planner API, MDR API  
**TYPICAL USERS:** Application developers, data engineers

---

### 🔄 LIF Translator API

**WHEN YOU NEED TO...**  
Transform data from your institution's systems (SIS, LMS, HR systems) into a standardized learner data format for integration and analysis.

**THIS SERVICE...**  
Converts data from various source formats into the LIF data model using configurable mappings, running within orchestrated data workflows.

**USE CASES:**

- Importing student records from your SIS into a unified data warehouse
- Standardizing learning activity data from multiple LMS platforms
- Converting HR employment records into learner experience data
- Preparing data for cross-institutional credential exchanges

**WORKS WITH:** MDR API (for mappings), Orchestrator API (runs in workflows)  
**TYPICAL USERS:** Data engineers, ETL developers

---

### 👤 LIF Identity Mapper API

**WHEN YOU NEED TO...**  
Match and link learner identities across different systems and institutions where the same person may have multiple IDs, email addresses, or identifying information.

**THIS SERVICE...**  
Resolves learner identities across systems and organizations, enabling accurate aggregation of records that belong to the same individual.

**USE CASES:**

- Connecting a student's community college records with their university records
- Linking learner identities across workforce training programs and educational institutions
- Merging records when students transfer between institutions
- Building comprehensive learner profiles from fragmented data sources

**WORKS WITH:** Query Planner API (provides identity mappings for queries)  
**TYPICAL USERS:** Data stewards, integration architects

---

### 📋 LIF MDR (Metadata Repository) API

**WHEN YOU NEED TO...**  
Define and manage how data from your source systems maps to the LIF data model, including schemas, field mappings, and transformation rules.

**THIS SERVICE...**  
Provides the backend for managing schemas, mapping configurations, and data translations used throughout the LIF ecosystem.

**USE CASES:**

- Configuring how your SIS fields map to standardized learner attributes
- Defining custom extensions to the LIF data model for institution-specific needs
- Managing data quality rules and validation logic
- Documenting data lineage and transformation logic

**WORKS WITH:** MDR UI (frontend), Translator API, GraphQL API  
**TYPICAL USERS:** Data architects, data governance teams

---

### 🖥️ LIF MDR UI

**WHEN YOU NEED TO...**  
Provide a user-friendly interface for data teams to configure mappings and manage metadata without writing code.

**THIS SERVICE...**  
Offers a web-based interface for configuring data mappings and managing the metadata repository.

**USE CASES:**

- Visually mapping source system fields to LIF data model attributes
- Testing and validating data transformations before deployment
- Managing versioning of mapping configurations
- Training non-technical staff on data integration processes

**WORKS WITH:** MDR API  
**TYPICAL USERS:** Data engineers, data stewards, business analysts

---

## Intelligence Layer

These services add AI and semantic capabilities on top of the core data infrastructure.

### 🤖 LIF Advisor API

**WHEN YOU NEED TO...**  
Build conversational interfaces that help users explore learner data, answer questions, or guide decision-making based on integrated learner information.

**THIS SERVICE...**  
Provides AI-powered advisory capabilities over learner data, enabling natural language interactions with complex educational and employment records.

**USE CASES:**

- "Student success advisor" chatbots for academic advisors
- Career guidance tools that analyze learner competencies and experiences
- Natural language querying of institutional data
- Personalized learning path recommendations based on prior learning
- Intervention suggestion engines for at-risk students

**WORKS WITH:** GraphQL API, Query Cache API, Advisor UI  
**TYPICAL USERS:** Student affairs, advising offices, EdTech product teams

---

### 💬 LIF Advisor UI

**WHEN YOU NEED TO...**  
Provide students or learners with a direct, conversational way to access and understand their educational and employment records.

**THIS SERVICE...**  
Offers a student-facing web interface for interacting with the AI-powered advisor.

**USE CASES:**

- Students asking "What courses do I need to graduate?"
- Learners exploring "What careers match my skills and experience?"
- Alumni reviewing their comprehensive learning history
- Job seekers understanding how to present their credentials to employers

**WORKS WITH:** Advisor API  
**TYPICAL USERS:** Students, learners, alumni

---

### 🔎 LIF Semantic Search MCP Server

**WHEN YOU NEED TO...**  
Enable AI tools and applications to discover and query learner data using natural language through the Model Context Protocol standard.

**THIS SERVICE...**  
Provides semantic search capabilities over learner data that can be accessed by MCP-compatible AI tools like Claude, Cursor, or custom AI applications.

**USE CASES:**

- Integrating learner data into AI development environments
- Enabling AI assistants to answer questions about student populations
- Building context-aware AI applications that understand learner records
- Creating custom AI tools that need semantic access to educational data

**WORKS WITH:** GraphQL API  
**TYPICAL USERS:** AI/ML developers, application developers integrating AI capabilities

---

## Infrastructure Services

These services provide the performance, optimization, and workflow orchestration necessary for production deployments.

### 💾 LIF Query Cache API

**WHEN YOU NEED TO...**  
Improve query performance and reduce load on source systems by caching learner data fragments and creating unified learner records.

**THIS SERVICE...**  
Stores LIF data model fragments from various sources (with metadata) and creates merged aggregate records for each learner.

**USE CASES:**

- Reducing response times for frequently accessed learner profiles
- Minimizing impact on production source systems during high query volumes
- Pre-aggregating learner records for real-time applications
- Supporting offline or disconnected access to learner data

**WORKS WITH:** Query Planner API (reads/writes cache)  
**TYPICAL USERS:** System administrators, platform engineers

---

### 🧠 LIF Query Planner API

**WHEN YOU NEED TO...**  
Intelligently route queries, determine data freshness requirements, and orchestrate data collection from multiple upstream sources.

**THIS SERVICE...**  
Acts as the query intelligence layer, checking cache availability, consulting the Identity Mapper for additional learner identities, and orchestrating data collection workflows when needed.

**USE CASES:**

- Optimizing query execution across multiple data sources
- Determining when cached data is sufficient vs. when fresh data is needed
- Coordinating complex queries that require identity resolution
- Managing data collection workflows for missing or stale data

**WORKS WITH:** GraphQL API (receives queries), Query Cache API, Identity Mapper API, Orchestrator API  
**TYPICAL USERS:** Platform engineers, DevOps teams

---

### 🔧 LIF Orchestrator API

**WHEN YOU NEED TO...**  
Integrate with existing workflow orchestration tools to manage data collection pipelines from upstream source systems.

**THIS SERVICE...**  
Provides a facade to external orchestration products (Dagster, Apache Airflow), enabling the Query Planner to trigger data collection workflows.

**USE CASES:**

- Scheduling regular data imports from institutional systems
- Triggering on-demand data collection when cache misses occur
- Managing complex ETL pipelines that include translation steps
- Coordinating data freshness across multiple source systems

**WORKS WITH:** Query Planner API (triggers workflows), Translator API (may be included in workflows)  
**TYPICAL USERS:** Data engineers, DevOps teams, workflow administrators

---

## How These Services Work Together

**Example Query Flow:**

1. A user queries the **GraphQL API** for a learner's complete record
2. **GraphQL API** forwards the query to **Query Planner API**
3. **Query Planner API** checks the **Query Cache API** for existing data
4. If data is missing or stale, **Query Planner API** consults **Identity Mapper API** for all known identities
5. **Query Planner API** triggers workflows via **Orchestrator API** to collect data
6. Orchestrator workflows fetch data from source systems, using **Translator API** if needed
7. Collected data is stored in **Query Cache API** as fragments and merged into an aggregate record
8. **GraphQL API** returns the complete learner record to the user

**Example AI-Powered Use Case:**

1. A student opens the **Advisor UI** and asks a question
2. **Advisor UI** sends the question to **Advisor API**
3. **Advisor API** queries learner data through **GraphQL API**
4. The query flows through the standard infrastructure (Query Planner, Cache, etc.)
5. **Advisor API** processes the data with AI and returns a natural language response
6. **Advisor UI** displays the conversational answer to the student

---

## Composing Solutions

Not every organization needs all services. Here are common deployment patterns:

**Simple Integration Pattern:**  
GraphQL API + Query Planner + Query Cache + Translator + MDR (API & UI)

- For organizations that want to standardize and query their learner data

**Advanced Analytics Pattern:**  
Add: Identity Mapper + Orchestrator API

- For multi-institutional scenarios requiring identity resolution and complex workflows

**AI-Enhanced Pattern:**  
Add: Advisor (API & UI) + Semantic Search MCP

- For organizations building AI-powered student services

**Full Platform:**  
All services

- For comprehensive learner data platforms serving multiple use cases
