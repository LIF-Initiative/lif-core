# ADR 0005: Unsupported Schema Formats

Date: 2025-09-05

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document for the MDR to support the ability to import schemas in JSON, XML, YAML, and framework/specifications like RDF.

Line 222 of the documentation regarding source data models previously stated: "Ability to upload schema of standard data models such as CEDS, Ed-Fi and other in <u>**JSON, XML, YAML, and framework/specifications like RDF and**</u> OpenAPI"


## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. We already support export/import via OpenAPI schema and it is unclear the degree to which there are use cases for these other formats.

## Alternatives
At this time, we recommend that organizations utilize the OpenAPI format when importing and exporting their data model schemas.

## Consequences
Fewer schema formats are supported, but support can always be added for more as needed.

## References
N/A
