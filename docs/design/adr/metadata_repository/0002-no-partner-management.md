# ADR 0002: No Partner Management

Date: 2025-09-05

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document for the MDR to support tracking of partner organization info and storage of credentials and URLs to access their data models.

Line 143 of the documentation previously stated: "A directory view of external partner LIF data models that have been imported <u>**organizations and credentials to retrieve their *partner-accessible LIF data models***</u> "

Line 254 of the documentation previously stated: "1.  The **MDR** serves as the LIF system of maintenance for data models, mappings and transformation. The system of record for LIF data models is a Github repo, and the system of record for transformations/mappings is the MDR. <u>**The MDR is the system of record for the list of partner organizations with their **LIF API** connection credentials for retrieving partner-accessible LIF data models**</u> ."

Under High Level Design, the following line used to be present: "**Partner organizations:** This includes a list of organizations that can act as a source for retrieving *partner-accessible LIF data models*. This also includes **LIF API** information for these organizations, along with additional metadata to successfully connect and fetch their data models"

The following section of functional requirements used to exist in the document:  
4. **LIF partner organizations**  
1. **Goal:** Designate partners to retrieve partner-accessible *LIF models*  
2. **Capabilities and Features**  
    1. Ability to maintain list of organizations identified with a unique Id to *retrieve partner-accessible* *LIF models*  
    2. Ability to maintain URL path for connecting to partner organization's **LIF API**  
    3. Ability to retrieve the *partner-accessible LIF model* from a partner organization and identify any changes from the previously retrieved model

## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. This is intrusive to organizations to have their URLs and security credentials stored in another organization's system.
2. The MDR does not currently support authentication, which would be a prerequisite to being able to support storage of authentication credentials.

## Alternatives
At this time, we recommend that organizations utilized the buttons in the MDR to download their schema, which they can then send to any desired partner organization via email, Google Drive, etc. Soon support should be added (TODO: LIF-99 & LIF-346) to be able to upload this OpenAPI schema to import a new Partner LIF model into the MDR.

## Consequences
This decision drastically reduces security concerns with the trade-off of the solution requiring manual steps to share data models between organizations.

## References
N/A
