
# Composer

Version 1.0.1

**Table of Contents**

[Overview](#overview) 

[Motivation](#motivation)

[Design Proposal](#design-proposal) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Key Concept](#key-concept) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF Record](#LIF-record) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF Fragment](#LIF-fragment) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Interaction with Other LIF Components](#interaction-with-other-lif-components) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Design Assumptions](#design-assumptions) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Design Requirements](#design-requirements) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Performance](#performance) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Concurrency](#concurrency) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[High Availability](#high-availability) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[High Level Design](#high-level-design) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Interface](#interface) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Workflow Model](#workflow-model) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Configuration](#configuration) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Dependencies](#dependencies) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Exceptions and Errors](#exceptions-and-errors) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF record build exception](#LIF-record-build-exception) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF record validation exception](#LIF-record-validation-exception) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Example Usage](#example-usage) [Detailed Design](#detailed-design) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Key Implementation Considerations](#key-implementation-considerations) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Implementation Design Principles](#implementation-design-principles) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Building LIF Record with LIF Fragments](#building-lif-record-with-lif-fragments) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Dealing with Array Elements](#dealing-with-array-elements) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Other Implementation Considerations](#cross-component-design-considerations) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Implementation Model](#implementation-model) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Tools and Technologies](#tools-and-technologies) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Implementation Requirements](#implementation-requirements) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Data Storage](#data-storage) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[State](#state) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Concurrency](#concurrency-1) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Sync/Async](#syncasync) 

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[External Services](#external-services) 

# Overview

The **Composer** component builds a more comprehensive LIF record with a given set of LIF fragments. It ensures that the **LIF API** receives a holistic LIF record composed of all the LIF fragments returned against a LIF query.

# Motivation

Any user query via the **LIF API** is broken down into one or more source-specific queries depending on the different data source systems required to fulfil the query. These data source systems can be internal to the organization or abstracted by a LIF **API** of the partnering organization. Based on these queries to individual data sources, multiple data pipelines may be triggered to produce a collection of disparate LIF fragments.

These LIF fragments need to be combined into a single holistic LIF record that represents the result of the **LIF API** query. The **LIF** **API** generates a request and receives results without being cognizant of individual source data systems required to provide the relevant data. Similarly, the **Orchestrator** data pipelines, and pipeline components operate on a source-specific query model regardless of how these individual results will serve the **LIF API** query. The **Composer** is the only component that provides a composition service in the Framework.

# Design Proposal

## Key Concept

### LIF Record

A LIF record is a holistic learner information dataset containing all of the parts required to satisfy a given **LIF API** query.

### LIF Fragment

A LIF fragment is a partial learner information dataset containing data for a given part of a holistic LIF record. A LIF fragment corresponds to a given part of the LIF record represented by a semantic path in a hierarchical structure relative to the root of the LIF record. Each LIF fragment contains a LIF fragment path along with the learner information in the LIF fragment. The learner information can be a JSON object or a collection of more than one JSON object. A LIF fragment path can be represented as a hierarchical dot path such as `person.identifier` ~~JSON Path expression such as `$.Person[?(@.Identifier[?(@.identifier == "person_identifier")])].Contact`~~

A sample collection of LIF fragments may look like the following:

```
lif_fragments = [
  {
    "fragment_path": "person.identifier",

    "fragment": {
      #sample json
    }
  }
]
```

The **Composer** component is a standalone component that combines multiple LIF fragments into one LIF record. A LIF record is assembled from a set of fragments each corresponding to a unique fragment path.

The **Composer** is invoked by the **LIF Cache**~~, **Query Planner,** or **LIF API**~~ to build LIF record with a collection of LIF fragments.

![](media/image_composer_1.png)

*Image 1: Simple diagram of the composition process in which the Composer turns LIF fragments into a holistic LIF record*

## Interaction with Other LIF Components

This component directly interacts with the **LIF Cache**~~, **Query Planner,** and **LIF API**. These components~~, which can invoke the **Composer** with a set of LIF fragments returned from the data request, and the **Composer** returns a LIF record with all the fragments appropriately consolidated.

## Design Assumptions

1.  The component is transient and does not maintain any state.

2.  ~~The component is highly available and is always ready to respond to any composition request.~~

3.  The component doesn't interact with any external resources except for the **LIF Cache**~~, **Query Planner,** and **LIF API** components that call~~ component that calls it for a composition request.

4.  The component is a shared library that is used directly within the code of the calling application. ~~The component runs as an independent function in its own runtime and returns the output LIF record to the calling component.~~

5.  The component presumes that the LIF fragments provided are correct and can be used to build a valid LIF record by using their respective fragment paths.

6.  The component expects the LIF fragments in JSON format and returns the LIF record in JSON format.

7.  The component currently serves only internal composition requests from the **LIF Cache** ~~and **Query Planner**~~and doesn't expose its services to any external entities.

8.  The component logs its run, and the log detail can be used to debug and assess its performance.

## Design Requirements

### Performance

(Possible Future Roadmap Item) The component should provide consistent performance irrespective of the size and complexity of the data structure it is composing.

### Concurrency

The **Composer** component should be able to address concurrent LIF record composition requests.

### High Availability

The component should always be available to serve incoming composition requests irrespective of the number of such requests and results of previous composition runs.

## High Level Design

The proposed design envisions the **Composer** component as a ~~serverless and stateless function that operates in a transient runtime environment~~stateless function that operates as a shared library.

The **Composer** component implements a Builder pattern to incrementally and iteratively build a LIF record with LIF fragments. Each LIF fragment is represented by a fragment path relative to the root and the respective JSON data. The component may also use the Strategy pattern to allow for different composition approaches if required.

~~Once initialized and invoked, the~~The **Composer** runs as a self-contained component without having to interact with any other LIF component to perform the composition. This is a light-weight component that does not maintain any information about a run. It also does not depend on any external entity to perform the composition.

The **Composer** component should be able to support composing LIF fragments of any shape into a LIF record.

### Interface

The **Composer** component supports following methods:

~~1.  **Initialize** - The **Composer** can be initialized with a valid LIF data model and any specific configuration to influence the composition outcome aligning the result to the client\'s expectations. These configurations are passed as valid JSON documents that are used by this component to initialize itself at the time of instantiation.~~

~~2.  **Run** - Once initialized, the **Composer** component can be invoked by calling its run method with a collection of LIF fragments. The component builds the target data set by incrementally adding each LIF fragment to the appropriate position specified by the fragment path.
 The LIF fragment path provides an absolute semantic path for a given LIF fragment relative to the root.
 After successfully building the target dataset, it validates that with the appropriate LIF data model before returning that to the calling component.~~

1. compose_json_with_single_fragment(lif_record_json: str, lif_fragment: LIFFragment) -> str:

2. compose_json_with_fragment_list(lif_record_json: str, lif_fragments: List[LIFFragment]) -> str:

3. compose_with_single_fragment(lif_record: LIFRecord, lif_fragment: LIFFragment) -> LIFRecord:

4. compose_with_fragment_list(lif_record: LIFRecord, lif_fragments: List[LIFFragment]) -> LIFRecord:

## Workflow Model

The **Composer** component is spun up when it's invoked by the **LIF Cache, Query Planner** or **LIF API** to build a LIF record from multiple LIF fragments. The **Composer** component may be invoked with a configuration specifying any specific composition instruction, such as rolling up an entity that has all its descendants with no value.

![](media/image_composer_2.png)

*Image 2: Simple workflow map for the initialization of the LIF Composer*

A successfully initialized **Composer** can then be invoked with a list of LIF fragments to get a corresponding LIF record.

![](media/image_composer_3.png)

*Image 3: Simple workflow map for the Composer's run process*

The **Composer** iterates through the list of LIF fragments, each containing a fragment path and the corresponding data, and then adds them to the output data structure. Once all the fragments are appropriately added to the output data structure, the resulting dataset is validated for a LIF data model and then returned to the caller component, which can be either the **LIF Cache, Query Planner** or the **LIF API**.

## Configuration

(Possible Future Roadmap Item) The **Composer** component may use specific configurations to influence the composition outcome. These configurations may include following information to influence the composition outcome:
```
{

"null_data_structure": "rollup\|remove",

"null_data_element": "remove"

}
```
These configurations are provided to the **Composer** component by the calling components including **LIF Cache,** **Query Planner,** and **LIF API**.

## Dependencies

## Exceptions and Errors

### LIF record build exception

This exception occurs when a **Composer** faces unexpected issues while assembling LIF fragments into a LIF record.

### LIF record validation exception

This exception occurs if a composed LIF record does not adhere to the LIF data model provided.

## Example Usage
```
from lif.composer.core import compose_with_fragment_list

updated_lif_record = compose_with_fragment_list(lif_record, lif_fragments)
```

## Possible Future Roadmap Items

[Issue #10: Improve Composer Performance](https://github.com/LIF-Initiative/lif-core/issues/10)

[Issue #11: Update Composer to Use Configuration](https://github.com/LIF-Initiative/lif-core/issues/11)
