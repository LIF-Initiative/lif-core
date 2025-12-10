# Add a New Data Source

Data sources are used by the **Orchestrator** to fulfill LIF queries. These sources can be open or require authN/authZ, and return data in a variety of formats. Data sources are configured through an adapter. You can have multiple data sources that use the same adapter. Reference implementations for 2 adapter flows are provided in the repository:
- LIF to LIF
- Example Data Source to LIF

To configure a non-LIF data source that requires custom authentication or custom data access (such as pagination) using the general docker compose file, the following guide is offered. This guide will show how to:
- Create a new adapter called `sis-data-source-to-lif` that supports a configured `Bearer` token for auth
- Configure the **Orchestrator** with a data source from `org1` called `acme-sis-data-source` using the new adapter
    - Note: the `acme-sis-data-source` is the _data source_ that configures the _adapter_ `sis-data-source-to-lif`. Multiple _data sources_ can use the same _adapter_.
- Setup a translation via the **MDR** to map the data source values into the LIF schema
- Confirm the data source can be queried through the **LIF API**

MDR Notes:
- _Base LIF_ is the Data Model with a blue square under `Data Model Selector`, labeled in the reference implementation as `LIF`.
- _Org LIF_ is the adopter's working organization model with a green square under `Data Model Selector`, labeled in the reference implementation as `StateU LIF`. The _Org LIF_ should include fields from the _Base LIF_ instead of custom fields where possible. You can rename the _Org LIF_ if you'd like.

The `example-data-source-rest-api-to-lif` adapter is the reference guide for this scenario. The flow offers flexibility in how the data source is leveraged and how generalized adopters want the _adapter_ to be for the various _data sources_.

1. Ensure the data source API is reachable by code running in the `dagster-code-location` container. The _data source_ configures an _adapter_. That _adapter_ is run in the `dagster-code-location` container. Likely shouldn't be an issue for the container to access the _data source_ endpoint, but if there are connection issues, consider the network between that container and the _data source_.

2. Clone `components/lif/data_source_adapters/example_data_source_rest_api_to_lif_adapter` into a sibling directory called `components/lif/data_source_adapters/sis_data_source_to_lif_adapter`.

3. Adjust the code in `sis_data_source_to_lif_adapter/adapter.py` to access the source API, including:
    - The auth token header to create a header `Authorization: Bearer [[TOKEN]]`
    - The context path for requesting data about a specific user (use the `self.lif_query_plan_part.person_id.identifier` for the user's identifier)

4. In the docker compose file for `dagster-code-location`, add the environment variables:
```
ADAPTERS__SIS_DATA_SOURCE_TO_LIF__ORG1_ACME_SIS_DATA_SOURCE__CREDENTIALS__HOST
ADAPTERS__SIS_DATA_SOURCE_TO_LIF__ORG1_ACME_SIS_DATA_SOURCE__CREDENTIALS__SCHEME
ADAPTERS__SIS_DATA_SOURCE_TO_LIF__ORG1_ACME_SIS_DATA_SOURCE__CREDENTIALS__TOKEN
```

5. In the **MDR** > `Data Models` tab, add a new `Source Data Model` that details how the data will be returned from the data source. It does not need to be exhaustive, just enough to cover the data that will be mapped into __LIF Schema__ paths. Take note of the **MDR** data source ID (in the context path of the **MDR** URL and at the top of the right handle panel when the data model itself is selected).

6. In the **MDR** > `Mappings` tab, select the new data source. In the center column, click `Create`. Using the built in controls, configure the translations from the new `Source Data Model` into the `Target Data Model` with the sticky lines.

7. If fields need to be added into the _Org LIF_ model, first review the `Data Models` > _Base LIF_ data model to see if the field already exists and just needs to be marked as included in _Org LIF_ model (`StateU LIF` > `Base LIF Inclusions` > find the field and tick the `Inc` checkbox). If the field does not exist, in the _Org LIF_ model, use the three vertical dots button to create the needed Entities and Attributes. Please do not modify the _Base LIF_!
    - If you update your _Org LIF_ data model, you should also update `components/lif/mdr_client/resources/openapi_constrained_with_interactions.json`. This file must be updated from http://localhost:8012/datamodels/open_api_schema/17?include_attr_md=true which is not currently exportable from the MDR UI.

8. Add a new block in `deployments/advisor-demo-docker/volumes/lif_query_planner/org1/information_sources_config_org1.yml` and enumerate the __LIF Schema__ JSON paths the data source will expose.
```
  - information_source_id: "org1-acme-sis-data-source"
    information_source_organization: "Org1"
    adapter_id: "sis-data-source-to-lif"
    ttl_hours: 24
    lif_fragment_paths: 
      - "person.Email.emailAddress"
      - "person.Address.addressCity"
      - "person.Address.addressState"
    translation:
      source_schema_id: "00" <-- Use the ID of the new data source
      target_schema_id: "17" <-- In the reference implementation, the Org LIF schema ID is constant (17)
```

9. After a docker compose restart, you should be able to query LIF via the **LIF API**, which is expose via the Strawberry GraphQL endpoint http://localhost:8010 with the following payload and have data from the new data source be returned.
```json
query MyQuery {
  person(
    filter: {identifier: {identifier: "[[user_id]]", identifierType: SCHOOL_ASSIGNED_NUMBER}}
  ) {
    Email {
      emailAddress
    },
    Address {
        addressCity,
        addressState
    }
  }
}
```

10. In order for the new data source to be leveraged in the Advisor, additional work needs to occur to tie in your users' IDs so the Advisor login details matches the user in the new data source. Currently, there's only the 6 static users for demo purposes. In the future, this should be a configurable effort with robust authN and the LIF **Identity Mapper**.
