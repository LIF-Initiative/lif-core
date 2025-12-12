# Add a New Data Source

Data sources are used by the **Orchestrator** to fulfill LIF queries. These sources can be open or require authN/authZ, and return data in a variety of formats. Data sources are configured through an adapter so you can have multiple data sources that use the same adapter. Reference implementations for 2 adapter flows are provided in the repository:
- LIF to LIF
- Example Data Source to LIF

To configure a non-LIF data source that requires custom authentication or custom data access (such as pagination) using the general docker compose file, the following guide is offered. This guide will show how to:
- Use a new data source that requires a `Bearer` token in the `Authorization` header, and responds to the endpoint `GET /user-details/[user-id]` with data in the format:
```json
{
    "user": {
        "details": {
            "mealPreference": "Omnivore",
            "address": {
                "city": "Fargo",
                "state": "NorthDakota",
            },
        }
    }
}
```
- Create a new adapter called `sis-data-source-to-lif` that supports a configured `Bearer` token for auth
- Configure the **Orchestrator** with a data source from `org1` called `acme-sis-data-source` using the new adapter
    - Note: the `acme-sis-data-source` is the _data source_ that configures the _adapter_ `sis-data-source-to-lif`
- Setup a translation via the **MDR** to map the data source values into the LIF schema
- Confirm the data can be queried through the **LIF API**

MDR Notes:
- _Base LIF_ is the Data Model with a blue square under `Data Model Selector`, labeled in the reference implementation as `LIF`.
- _Org LIF_ is the adopter's working organization model with a green square under `Data Model Selector`, labeled in the reference implementation as `StateU LIF`. The _Org LIF_ should include fields from the _Base LIF_ instead of custom fields where possible. You can rename the _Org LIF_ if you'd like.
- All entities in _Org LIF_ should be _Arrays_. 
- Attributes can be either _Arrays_ or objects
- To be clear, for data models other than _Base LIF_ and _Org LIF_, entities do not have to be arrays.
- There is a known bug in the **MDR** can manifests itself as an authorization error (another bug), but is really a database issue. The workarounds are in the tickets:
    - https://github.com/LIF-Initiative/lif-core/issues/47
    - https://github.com/LIF-Initiative/lif-core/issues/42

The `example-data-source-rest-api-to-lif` adapter is the reference implementation for this guide. The flow offers flexibility in how the data source is leveraged and how generalized adopters want the _adapter_ to be for the various _data sources_.

1. Ensure the data source API is reachable by code running in the `dagster-code-location` container. The _data source_ configures an _adapter_. That _adapter_ is run in the `dagster-code-location` container. It likely shouldn't be an issue for the container to access the _data source_ endpoint, but if there are connection issues, consider reviewing the network between that container and the _data source_.
    - If serving the ACME SIS Data Source from the host's localhost network, remember to specify the `..._HOST` configuration further along in this guide as `host.docker.internal[:PORT]`

2. Clone `components/lif/data_source_adapters/example_data_source_rest_api_to_lif_adapter` into a sibling directory called `components/lif/data_source_adapters/sis_data_source_to_lif_adapter`.

3. Adjust the code in `sis_data_source_to_lif_adapter/adapter.py` to access the source API, including:
    - Change the class name to `SisDataSourceToLIFAdapter`
    - The `adapter_id` should be changed to `sis-data-source-to-lif`
    - Adjust the auth token header to send the header `Authorization: Bearer [[TOKEN]]`
    - Adjust the context path for requesting data about a specific user (use the `self.lif_query_plan_part.person_id.identifier` for the user's identifier), such as:
        ```python
        source_url = f"{self.scheme}://{self.host}/user-details/{ident}"
        ```
    - Change the various message that reference 'Example Data Source REST API' to your data source name

4. Adjust the import code in `components/lif/data_source_adapters/sis_data_source_to_lif_adapter/__init__.py` to reflect the new adapter name of `SisDataSourceToLIFAdapter`

4. Add the adapter id (`sis-data-source-to-lif`) into the `components/lif/data_source_adapters/__init__.py::_EXTERNAL_ADAPTERS` map and add the adapter import:
    ```python
    ...
    from .sis_data_source_to_lif_adapter.adapter import SisDataSourceToLIFAdapter
    ...
    _EXTERNAL_ADAPTERS = {
        ...
        "sis-data-source-to-lif": SisDataSourceToLIFAdapter,
    }
    ```

4. In the docker compose file for `dagster-code-location`, add the following environment variables with the appropriate configuration for the data source: 
    ```
    ADAPTERS__SIS_DATA_SOURCE_TO_LIF__ORG1_ACME_SIS_DATA_SOURCE__CREDENTIALS__HOST
    ADAPTERS__SIS_DATA_SOURCE_TO_LIF__ORG1_ACME_SIS_DATA_SOURCE__CREDENTIALS__SCHEME
    ADAPTERS__SIS_DATA_SOURCE_TO_LIF__ORG1_ACME_SIS_DATA_SOURCE__CREDENTIALS__TOKEN
    ```

    - Note the format is `ADAPTERS__[[ADAPTER_ID]]__[[ORG]][[DATA_SOURCE_ID]]__CREDENTIALS__...`

4. Rebuild and start docker compose with `deployments/advisor-demo-docker` (from the root of the repo, you can run `docker-compose -f deployments/advisor-demo-docker/docker-compose.yml up --build`)

5. In the **MDR** > `Data Models` tab, add a new `SourceSchema` Data Model that describes how the data will be returned from the data source. It does not need to be exhaustive, just enough to cover the data that will be mapped into the _Org LIF_ schema paths. Take note of the **MDR** data source ID (in the context path of the **MDR** URL and at the top of the right hand panel when the data model itself is selected). This ID will be used to configure the translation flow later on.
    - The unique name of entities, attributes, etc should be a 'dot path'. For example, if the source schema contains `user > details > address > state`, the `name` for the **MDR** entry should be _state_, and the `unique name` should be _user.details.address.state_.
    - Only attributes are able to be mapped, so for the above case, _state_ should be an attribute.

6. In the **MDR** > `Mappings` tab, select the new data source. In the center column, click `Create`. Using the built in controls, configure the translations from the new `Source Data Model` into the `Target Data Model` with the sticky lines.
    - Reminder: Only attributes can be mapped.
    - Due to a bug in the user flow, after mapping an attribute, manually lower case the JSONata _expression_ by double clicking on the sticky line and adjusting the field. For example, given the expression:
        ```
        { "Person": [{ "Contact": [{ "Address": [{ "addressCity": user.details.address.state }] }] }] }
        ```
        Lower case `Person`, `Contact`, and `Address` to be:
        ```
        { "person": [{ "contact": [{ "address": [{ "addressCity": user.details.address.state }] }] }] }
        ```
    - Due to a **MDR** UX bug, sometimes the mappings don't always appear ( https://github.com/LIF-Initiative/lif-core/issues/44 ). See the workarounds in the issue ticket if this occurs.

7. If target fields in the mappings need to be added into the _Org LIF_ model, first review the `Data Models` > _Base LIF_ data model to see if the field already exists and just needs to be marked as included in _Org LIF_ model (You can review this by accessing `StateU LIF` > `Base LIF Inclusions` > find the field and tick the `Inc` checkbox). If the field does not exist in the _Base LIF_ model, then in the _Org LIF_ model, use the three vertical dots button to create the needed entities and attributes. Please do not modify the _Base LIF_ model.
    - If creating new entities or attributes:
        - Remember the dot.path for the unique name
        - Ensure the new fields have `Array` set to `Yes`
    - If you update your _Org LIF_ data model, you should also update `components/lif/mdr_client/resources/openapi_constrained_with_interactions.json`. This file must be updated from http://localhost:8012/datamodels/open_api_schema/17?include_attr_md=true which is not currently exportable from the **MDR** UI. You will need to include the user's Bearer token from using **MDR**'s UI in an `Authorization` header when retrieving the download, such as `curl 'http://localhost:8012/datamodels/open_api_schema/17?include_attr_md=true' -H 'Authorization: Bearer ...'  > components/lif/mdr_client/resources/openapi_constrained_with_interactions.json`. After changing the json file, rebuild and start docker compose (the rebuild/start can be done in a later step as well).
    - If the GraphQL schema isn't validating in the Strawberry GraphQL UI (`localhost:8010`) the way you'd expect, the json file needs to be updated (or the _Org LIF_ data model needs adjustment)

8. Add a new block in `deployments/advisor-demo-docker/volumes/lif_query_planner/org1/information_sources_config_org1.yml` and enumerate the _Org LIF_ schema JSON paths the data source will populate (note the population occurs during translation). Only specify 2 nodes deep: for `person.contact.address.addressState`, just add `person.contact`.
    ```yaml
    - information_source_id: "org1-acme-sis-data-source"
        information_source_organization: "Org1"
        adapter_id: "sis-data-source-to-lif"
        ttl_hours: 24
        lif_fragment_paths: 
        - "person.contact"
        - "person.custom"
        translation:
        source_schema_id: "00" <-- Use the ID of the new data source
        target_schema_id: "17" <-- In the reference implementation, the Org LIF schema ID is constant (17)
    ```

9. After a docker compose rebuild and start, you should be able to query LIF via the **LIF API**, which is exposed via the Strawberry GraphQL endpoint http://localhost:8010 with the following payload. Note `employmentPreferences > organizationTypes` is populated from `org1-example-data-source`, and the `custom > ...` and `contact > ...` are populated from `acme-sis-data-source`.
    ```json
    query MyQuery {
    person(
        filter: {identifier: {identifier: "100001", identifierType: "SCHOOL_ASSIGNED_NUMBER"}}
    ) {
        employmentPreferences {
        organizationTypes
        },
        custom {
        mealPreference
        },
        contact {
        address {
            addressCity
            addressState
        }
        }
    }
    }
    ```

10. In order for the new data source to be leveraged in the Advisor, additional work needs to occur:
    - The MCP service needs to be aware additional _Org LIF_ schema changes
    - Your organization's user IDs needs to be available in the Advisor API so the Advisor login details matches the appropriate user in the new data source. Currently, there's only the 6 static users for demo purposes. In the future, this should be a configurable effort with robust authN and the LIF **Identity Mapper**.

## Troubleshooting

### Check Dagster
At times, the Dagster run will not complete as expected and can offer insights on what happened
- Access Dagster at http://localhost:3000/runs/
- Navigate to the latest run
- Navigate to the sub process for the SIS data adapter and review the messages

#### Empty fragment paths
There is a known issue when a translation yields an empty LIF fragment, Dagster's job run will fail when trying to save the results to the **LIF Query Planner**.

If your LIF Fragment is empty, but it shouldn't be, check that the JSONata expressions are lower-cased as noted previously in this guide.

### Clear the Cache
The **LIF Cache** service uses mongoDB to store LIF Query results so the Orchestration process does not always need to be executed. There is a TTL on the cache (default of 24 hours), and at times, it's desireable for updates to occur sooner then the TTL. 

To clear the cache, stop the services, delete the docker container `mongodb-org1`, and restart docker compose.

Take care to not remove other volumes, as this might affect, in part, the **MDR** configuration previously described in this guide.
