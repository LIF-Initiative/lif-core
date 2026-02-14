import datetime as dt
import hashlib
import os
import requests
import time
import warnings
from dataclasses import dataclass
from typing import Dict, List

import dagster as dg

from lif.data_source_adapters import get_adapter_by_id, get_adapter_class_by_id
from lif.datatypes import LIFFragment, LIFQueryPlanPart, OrchestratorJobQueryPlanPartResults, OrchestratorJobResults
from lif.query_planner_service.util import adjust_lif_fragments_for_initial_orchestrator_simplification

QUERY_PLANNER_RESULTS_BASE_URL = os.getenv("LIF_QUERY_PLANNER_RESULTS_BASE_URL")
QUERY_PLANNER_RESULTS_TOKEN = os.getenv("LIF_QUERY_PLANNER_RESULTS_TOKEN")

TRANSLATOR_BASE_URL = os.getenv("LIF_TRANSLATOR_BASE_URL")
TRANSLATOR_TOKEN = os.getenv("LIF_TRANSLATOR_TOKEN")

MAX_RETRIES_SUBGRAPH = 3  # Not currently possible to get from dg.OpExecutionContext
RETRY_POLICY_SUBGRAPH = dg.RetryPolicy(
    max_retries=MAX_RETRIES_SUBGRAPH, delay=0.2, backoff=dg.Backoff.EXPONENTIAL, jitter=dg.Jitter.PLUS_MINUS
)


class SharedOpConfig(dg.ConfigurableResource):
    lif_query_plan_parts: List[dict] = []


@dataclass
class SubgraphResult:
    lif_query_plan_part: LIFQueryPlanPart
    data: OrchestratorJobQueryPlanPartResults | dict | list | None


def get_credentials_for_adapter(adapter_id: str, information_source_id: str) -> Dict[str, str]:
    """
    Get credentials using DLT-style naming from environment variables.
    Pattern: ADAPTERS__<ADAPTER_ID>__<INFORMATION_SOURCE_ID>__CREDENTIALS__<CREDENTIAL_KEY>

    Note that adapter_id dashes are converted to underscores in environment variable names.
    """
    adapter_class = get_adapter_class_by_id(adapter_id)

    if not hasattr(adapter_class, "credential_keys"):
        return {}

    credentials = {}
    prefix = f"ADAPTERS__{adapter_id.replace('-', '_').upper()}__{information_source_id.replace('-', '_').upper()}__CREDENTIALS"
    expected_keys = adapter_class.credential_keys

    for cred_key in expected_keys:
        env_var_name = f"{prefix}__{cred_key.upper()}"
        value = os.getenv(env_var_name)
        if value:
            credentials[cred_key] = value
        else:
            warnings.warn(
                f"Missing expected credential key '{cred_key}' for adapter '{adapter_id}' and source '{information_source_id}'"
            )

    return credentials


def generate_mapping_key(part: dict) -> str:
    if (
        part.get("adapter_id") is None
        or part.get("information_source_id") is None
        or part.get("person_id", {}).get("identifier") is None
    ):
        raise ValueError(
            "Part must contain 'adapter_id', 'information_source_id', and 'person_id.identifier' to generate mapping key."
        )
    base_key = f"{part['adapter_id'].replace('-', '_')}__{part['information_source_id'].replace('-', '_')}__{part['person_id']['identifier']}"
    unique_suffix = str(time.time()).replace(".", "_")
    short_hash = hashlib.sha256(unique_suffix.encode()).hexdigest()[:8]

    return f"{base_key}__{short_hash}"


@dg.op(out=dg.DynamicOut())
def create_dynamic_pipelines(context: dg.OpExecutionContext, config_resource: SharedOpConfig):
    for part in config_resource.lif_query_plan_parts:
        query_plan_part = LIFQueryPlanPart(**part)
        context.log.info(f"Creating dynamic pipeline for part: {part}")
        yield dg.DynamicOutput(query_plan_part, mapping_key=generate_mapping_key(part))


@dg.op(out=dg.Out(is_required=False), retry_policy=RETRY_POLICY_SUBGRAPH)
def run_lif_adapter(context: dg.OpExecutionContext, lif_query_plan_part: LIFQueryPlanPart) -> SubgraphResult:
    try:
        # TODO: How does registering an external adapter work here?
        adapter_id = lif_query_plan_part.adapter_id
        information_source_id = lif_query_plan_part.information_source_id

        credentials = get_credentials_for_adapter(adapter_id, information_source_id)

        context.log.info(f"Retrieved credentials for adapter '{adapter_id}' with source '{information_source_id}'")
        context.log.info(f"Available credential keys from dagster environment: {list(credentials.keys())}")

        # Get adapter with credentials (currently hard-coded to LIFToLIFAdapter below)
        adapter = get_adapter_by_id(adapter_id, lif_query_plan_part=lif_query_plan_part, credentials=credentials)

        result = adapter.run()

        context.log.info(f"Adapter '{adapter_id}' executed successfully with data: {result}")

        return SubgraphResult(lif_query_plan_part=lif_query_plan_part, data=result)
    except Exception as e:
        if context.retry_number >= MAX_RETRIES_SUBGRAPH - 1:
            context.log.error(
                f"run_lif_adapter failed after {context.retry_number} retries for adapter_id={adapter_id} information_source_id={information_source_id}: {e}",
                exc_info=True,
            )
            return SubgraphResult(lif_query_plan_part=lif_query_plan_part, data=None)
        else:
            raise


@dg.op(out=dg.Out(is_required=False), retry_policy=RETRY_POLICY_SUBGRAPH)
def run_translation(
    context: dg.OpExecutionContext, config_resource: SharedOpConfig, upstream_input: SubgraphResult
) -> SubgraphResult:
    if upstream_input.lif_query_plan_part.translation is None:
        context.log.info("Skipping Translation as it's not part of the query plan.")
        return upstream_input

    if upstream_input.data is None:
        context.log.info("Skipping Translation as there is no data from the adapter.")
        return SubgraphResult(lif_query_plan_part=upstream_input.lif_query_plan_part, data=None)

    context.log.info(f"Running Translation with data: {upstream_input.data}")

    try:
        # Translation logic goes here (currently pass-through)
        url = f"{TRANSLATOR_BASE_URL}/translate/source/{upstream_input.lif_query_plan_part.translation.source_schema_id}/target/{upstream_input.lif_query_plan_part.translation.target_schema_id}"
        headers = {"Content-Type": "application/json", "User-Agent": "LIF-Orchestrator"}
        if TRANSLATOR_TOKEN:
            headers["Authorization"] = f"Bearer {TRANSLATOR_TOKEN}"

        response = requests.post(url, json=upstream_input.data, headers=headers)
        if not response.ok:
            context.log.info(f"Response {response.status_code}: {response.text}")
        response.raise_for_status()

        translated_data = response.json()

        context.log.info(f"Translation API response: {translated_data}")

        # temporary method to extract fragments based on requested paths
        person_all_fragment = LIFFragment(fragment_path="person.all", fragment=[translated_data])

        context.log.info(f"Person all fragment: {person_all_fragment}")

        req_fragments_in_translated = adjust_lif_fragments_for_initial_orchestrator_simplification(
            lif_fragments=[person_all_fragment],
            desired_fragment_paths=upstream_input.lif_query_plan_part.lif_fragment_paths,
        )

        context.log.info(f"Requested fragments in translated data: {req_fragments_in_translated}")

        fragments = []

        # populate LIFFragments based on requested fragment paths, even if no data was returned
        for req_fragment_path in upstream_input.lif_query_plan_part.lif_fragment_paths:
            fragment = LIFFragment(fragment_path=req_fragment_path, fragment=[])
            for existing_fragment in req_fragments_in_translated:
                if existing_fragment.fragment_path == req_fragment_path:
                    fragment = existing_fragment
                    break
            fragments.append(fragment)

        result = OrchestratorJobQueryPlanPartResults(
            information_source_id=upstream_input.lif_query_plan_part.information_source_id,
            adapter_id=upstream_input.lif_query_plan_part.adapter_id,
            data_timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            person_id=upstream_input.lif_query_plan_part.person_id,
            fragments=fragments,
            error=None,
        )

        context.log.info(f"Translation result: {result}")

        return SubgraphResult(lif_query_plan_part=upstream_input.lif_query_plan_part, data=result)

    except Exception as e:
        if context.retry_number >= MAX_RETRIES_SUBGRAPH - 1:
            context.log.error(f"run_translation failed after {context.retry_number} retries: {e}", exc_info=True)
            return SubgraphResult(lif_query_plan_part=upstream_input.lif_query_plan_part, data=None)
        else:
            raise


@dg.graph
def process_pipeline_subgraph(lif_query_plan_part):
    data = run_lif_adapter(lif_query_plan_part)
    # TODO: Add dynamic skipping of translation based on adapter type or presence of translation key
    result = run_translation(data)
    return result


@dg.op
def send_results_to_query_planner(
    context: dg.OpExecutionContext, config_resource: SharedOpConfig, results: List[SubgraphResult]
) -> None:
    # Fan-in operation that receives all results from dynamic pipelines

    # Build query plan part results. Ensure all expected parts are represented.
    query_plan_part_results = []
    for p in config_resource.lif_query_plan_parts:
        part = LIFQueryPlanPart(**p)
        matching_results = [
            # Filter out None entries (pipelines that failed or were skipped) before matching
            res
            for res in results
            if res is not None
            and res.data is not None
            and res.lif_query_plan_part.information_source_id == part.information_source_id
            and res.lif_query_plan_part.adapter_id == part.adapter_id
        ]

        if len(matching_results) > 1:
            context.log.warning(f"Multiple results found for part {part}. Using the first one.")

        if matching_results:
            query_plan_part_results.append(matching_results[0].data)
        else:
            query_plan_part_results.append(
                OrchestratorJobQueryPlanPartResults(
                    information_source_id=part.information_source_id,
                    adapter_id=part.adapter_id,
                    data_timestamp=None,
                    person_id=part.person_id,
                    fragments=[],
                    error="Pipeline did not run or failed.",
                )
            )

    # build the final job results
    job_results = OrchestratorJobResults(run_id=context.run_id, query_plan_part_results=query_plan_part_results)

    # TODO: Change to debug level once stable
    context.log.info(f"Final Orchestrator Job Results: \n\n{job_results.model_dump_json(indent=2)}")

    endpoint = f"{QUERY_PLANNER_RESULTS_BASE_URL}/orchestration/results"
    headers = {"Content-Type": "application/json", "User-Agent": "LIF-Orchestrator"}
    if QUERY_PLANNER_RESULTS_TOKEN:
        headers["Authorization"] = f"Bearer {QUERY_PLANNER_RESULTS_TOKEN}"

    response = requests.post(endpoint, json=job_results.model_dump(), headers=headers)
    if not response.ok:
        context.log.info(f"Response {response.status_code}: {response.text}")
    response.raise_for_status()
    context.log.debug(f"Results successfully sent to Query Planner at {endpoint}")


@dg.graph
def dynamic_pipeline_graph():
    pipelines = create_dynamic_pipelines()
    results = pipelines.map(process_pipeline_subgraph)
    send_results_to_query_planner(results.collect())


# Example configuration for testing that will show up in the UI
TEST_LIF_QUERY_PLAN_PARTS = [
    {
        "information_source_id": "org2",
        "adapter_id": "lif-to-lif",
        "person_id": {"identifier": "100001", "identifierType": "School-assigned number"},
        "lif_fragment_paths": ["person.positionPreferences", "person.employmentLearningExperience"],
    },
    {
        "information_source_id": "org3",
        "adapter_id": "lif-to-lif",
        "person_id": {"identifier": "100001", "identifierType": "School-assigned number"},
        "lif_fragment_paths": ["person.credentialAward", "person.courseLearningExperience"],
    },
    {
        "information_source_id": "org1-example-data-source",
        "adapter_id": "example-data-source-rest-api-to-lif",
        "person_id": {"identifier": "100001", "identifierType": "School-assigned number"},
        "lif_fragment_paths": ["person.employmentPreferences"],
        "translation": {"source_schema_id": "26", "target_schema_id": "17"},
    },
]

dynamic_pipeline_job = dynamic_pipeline_graph.to_job(
    name="lif_dynamic_pipeline_job",
    executor_def=dg.in_process_executor,
    resource_defs={"config_resource": SharedOpConfig(lif_query_plan_parts=TEST_LIF_QUERY_PLAN_PARTS)},
    config=dg.RunConfig(resources={"config_resource": {"config": {"lif_query_plan_parts": TEST_LIF_QUERY_PLAN_PARTS}}}),
)
