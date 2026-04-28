# LIF Query Cache

Version 1.0.0

**Table of Contents**

[Overview](#overview) 

[Motivation](#motivation) 

[Design Proposal](#design-proposal)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Key Concept](#key-concepts)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF Record](#LIF-record)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF Fragment](#LIF-fragment)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF Query Result](#LIF-query-result)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Cache Storage](#cache-storage)

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

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[LIF Record Not Found Exception](#LIF-record-not-found-exception)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Cache not available exception](#cache-not-available-exception)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Example Usage](#example-usage)

[Possible Future Roadmap Items](#possible-future-roadmap-items)

# Overview

The **Query Cache** component provides caching support for previous LIF queries in order to save time and cost needed to run the **Orchestrator** to fetch data for a query that can be satisfied by the cache.

# Motivation

Serving a LIF query involves a significant amount of infrastructure, especially regarding the **Orchestrator**-managed data pipelines (**Pipeline Tasks**). Depending on the number of source systems required, there may be many data pipelines operating in parallel fetching data from the sources and translating them.

By saving the results of prior queries, we can serve the same query multiple times without having to invoke data pipelines, which saves resources and improves LIF's response time.

The **Query Cache** allows the user to incrementally and iteratively build and update learner data as queries related to a learner are fulfilled. Maintaining the learner data as a holistic LIF record in the cache simplifies the process of fulfilling queries as the data set becomes increasingly more comprehensive.

# Design Proposal

The **Query Cache** component stores and maintains learner data as a LIF record that is incrementally built and updated as it receives new LIF fragments. The cache also stores negative results indicating that no results were returned by the query. The component maintains read-optimized and write-optimized stores. While the read-optimized store maintains the holistic LIF record for serving any LIF query, the write-optimized store holds the incoming result of source LIF queries in form of LIF fragments.

![](media/image_query_cache_3.png)

*Image 1: A simple diagram depicting the relationships between the Query Planner and Query Cache*

The **Query Cache** component uses the **Composer** to process the collection of LIF fragments in order to create or update a LIF record in the read-optimized store. In addition to the read-optimized and write-optimized stores, the component also has a caching service that provides the query and update functions. The **Query Cache** component can implement appropriate storage technologies and mechanisms to support required storage and query patterns.

## Key Concepts

### LIF Record

A LIF record is a single holistic dataset that contains all information in the cache related to one learner. A LIF record is represented as a JSON document with a root node of the learner.

### LIF Fragment

A LIF fragment is a partial learner information dataset containing data corresponding to a specific branch of the LIF record. A LIF fragment contains the fragment path and the corresponding LIF data structure. The fragment path is the semantic path of the associated data structure relative to the root of the LIF record. This fragment path can be represented as a ~~JSON Path expression such as \$.person.attendance~~ hierarchical dot path such as *person.identifier*.

A sample collection of LIF fragments looks like the following:

```
{
	"fragment_path": "person.identifier",
	"fragment": {
		// LIF data part
	}
}
```

### LIF Query Result

A LIF query result is a collection of one or more LIF ~~fragments with additional~~ records that includes metadata information such as source and timestamp. ~~LIF query results are generated by data pipelines that fetch data from different source systems.~~

A sample query result can be represented with the following JSON:

```
[
	{
		"person": [
			{
				"identifier": [
					{
						"informationSourceId": "Org1",
						"identifier": "100123",
						"identifierType": "SCHOOL_ASSIGNED_NUMBER"
					}
				]
			}
		]
	},
	{
		"person": [
			{
				"identifier": [
					{
						"informationSourceId": "Org2",
						"identifier": "100789",
						"identifierType": "SCHOOL_ASSIGNED_NUMBER"
					}
				]
			}
		]
	}
]
```

### Cache Storage

The **Query Cache** employs a storage and retrieval mechanism for LIF query and corresponding collections of LIF fragments. The cache storage maintains additional metadata on fragments, such as timestamp and time_to_live parameters. These parameters help the **Query Cache** determine if the respective query results can still serve the respective query, or if they are expired and require data to be fetched from the corresponding source system.

Cache Storage can be split into two separate components, read-optimized storage and write-optimized storage, if usage patterns require improved performance.

* Read-Optimized Storage: Storage implementation optimized for fast read operations.  This would store the LIF Records.
* (Possible Future Roadmap Item) Write-Optimized Storage: Storage implementation optimized for fast write operations.  This would store the LIF Fragments returned from the Orchestrator.

### Sync Service (Possible Future Roadmap Item)

The sync service is responsible for taking the LIF Records from the write-optimized storage and incorporating the data into the LIF Records stored in the read-optimized storage.

### Immutability (Possible Future Roadmap Item)

LIF records have a characteristic of "immutability" in that branches of a LIF record do not change after they are finalized (e.g., final grades and attendance cannot be changed, demographic information is managed with effective dates, etc.). This allows query results to be treated as immutable. This also applies to negative results. LIF fragments submitted to the cache have a time_to_live parameter and will only be considered immutable if time_to_live is not specified (or zero). The **Query Planner** can use immutability to optimize its query plans.

## Interaction with Other LIF Components

The **Query Planner** component interacts with **Query Cache** to store the query result and then search for it by a LIF query.

## Design Assumptions

1.  The **Query Cache** component is not a system of record. The only objective the component has is to improve performance by maintaining a LIF record with frequent updates from any data pipeline runs against a given LIF query.

2.  The Cache Storage part is persistent and optimized for both read and write operations.

3.  The Cache Service part is stateless and can be implemented as a serverless function.

4.  The Cache Service responds in sync mode.

5.  The Cache Service provides separate end points for querying LIF records and saving LIF fragments.

6.  The component should provide fast read and write responses irrespective of the size of the cache and volume and frequency of such requests.

7.  The component may implement appropriate storage and query mechanisms to support different possible cache storage and query patterns.

8.  The component should be able to use different storage technologies on a plug-and-play basis.

9.  The component does not perform any validation for the collection of LIF fragments being stored.

10. The component expects LIF fragments in JSON format and represented by a valid JSON document conforming to the **LIF Data Model**.

11. The component logs its run, and the log detail can be used to debug and assess its performance.

12. The component uses the **Composer** to process a collection of LIF fragments to build or update the respective LIF record. The **Composer** may compose the fragments into a larger LIF record if they are immutable.

13. The **Query Cache** component must be designed for high availability, performance, and consistency in LIF structure.

## Design Requirements

### Performance

The component provides consistent performance ensuring fast response time for querying LIF records and saving LIF query results.

### Concurrency

The concurrency of the component will be limited by the underlying caching implementation. The implementation needs to support the required concurrency limit.

### High Availability

The component should support high availability by implementing sufficient redundancy with backup and restore capabilities.

## High Level Design

The proposed design envisions the **Composer** component as a service with persistent cache storage system implemented using a configurable storage mechanism and storage system. The **Query Cache** storage design considers following key aspects:

1.  **Throughput (Latency vs Request Processing Rate):** The cache service and the cache storage can be implemented to support desired throughput.

2.  **Caching strategy:** A read-through and write-through strategy may be implemented if a secondary offline or slower response time cache is implemented, but it is not required in the initial design. A secondary cache storage would only be implemented for the read-optimized store.

3.  **Cache eviction strategy:** An appropriate cache eviction strategy can be implemented. Recommended ones include least recently used and least frequently used.

This component employs the Proxy design pattern for the Cache Storage, enabling the Cache Service to query the storage without reference to where the real data exists. The Cache Storage may also use the Flyweight design pattern to save memory by reusing the same copy of a LIF record for serving different requests for a given learner.

The **Query Cache** includes two key components:

1.  **Cache service** - A serverless function that connects with the underlying cache to provide the mechanism to query LIF records and to update the cache with LIF fragments. This component provides an interface to the external component while also abstracting the underlying cache storage implementation, allowing for using read-optimized cache to serve query requests and write-optimized cache to serve update requests. This provides flexibility to upgrade the caching capability without disrupting the service.

2.  **Cache storage** - This is the caching implementation that supports read-optimized and write-optimized storage to optimally serve read and write requests. The cache storage can employ different storage mechanisms and technologies to provide desired caching performance based on common or frequent query and update patterns. In a distributed environment, the **Query Cache** component is implemented using a shared caching approach ensuring that the same cache is accessed from the cache service for requests ensuring consistency of the data being returned. In this environment, the cache storage can be implemented as a distributed cache to ensure high-availability and fault-tolerance.

![](media/image_query_cache_2.png)

*Image 2: Diagram depicting the interactions between the services, stores, and external Composer*

### Interface

The **Query Cache** component supports following functions:

1.  **Save** - The **Query Cache** can be invoked to save a collection of LIF fragments. A LIF fragment contains a fragment path and the corresponding JSON dataset. The cache request may also contain other metadata information such as source identifier, time_to_live, and others to help the **Query Cache** component appropriately process these fragments. Incoming LIF fragments are saved in the write-optimized store.

2.  **Load** - The primary responsibility of **Query Cache** is to allow for querying one or more LIF records based on the **LIF API** query. This function uses the read-optimized store to search available LIF records. It may also look in the write-optimized store for required data not found or expired considering the possibility of any related LIF fragments not yet synced with the read-optimized store. It returns a partial LIF record with appropriate parts to fulfil the **LIF API** request. It may contain Null values for the part for which it couldn't find the data in the cache.

## Workflow Model

The **Query Cache** component is available as a service providing the functions to save LIF fragments and query LIF records. The following diagrams show the workflow for these two functions.

![](media/image_query_cache_1.png)

*Image 3: Simple workflow map of the save function of the **Query Cache***

The **Query Cache** uses multiple levels of storage to provide appropriate response time given the frequencies of LIF queries.

The **Query Cache** returns a collection of partial LIF records using the load method.

![](media/image_query_cache_5.png)

*Image 4: Simple workflow map of the load function of the **Query Cache***

In addition to these key functions for its clients, the **Query Cache** also runs a sync service internally to incrementally and iteratively build and update learner-centric LIF records in the read-optimized store with new LIF fragments from the write-optimized store.

![](media/image_query_cache_4.png)

*Image 5: Simple workflow map of the sync service of the **Query Cache***

## Configuration

The **Query Cache** component may use specific configurations to provide the desired level of performance and outcome. These configurations may include the following information to align the services offered :

```
{
	"caches": {
		"read_cache": {
			"storage_type": "",
			"connection_string": ""
	},
	"write_cache": {
		"storage_type": "",
		"connection_string": ""
		},
	},
	"sync": {
		"mode": "scheduled|on_demand"
	}
}
```

These configurations are provided to the **Query Cache** by the underlying infrastructure settings, and the Caching service component is spun up with the appropriate configuration as specified.

## Dependencies

The quality and performance of this component depends on the capabilities of the specific technologies used to implement the cache storage.

## Exceptions and Errors

### LIF Record Not Found Exception

This exception occurs when the **Query Cache** is not able to find data for a given query.

### Cache not available exception

This exception occurs if the **Query Cache** is not able to connect to its underlying cache storage.

## Example Usage

```
query_cache = QueryCache(config)
query_cache.save(lif_fragments)
query_cache.load(lif_query)
```

# Possible Future Roadmap Items

[Issue #31: Query Cache: Add Immutability of LIF Record Branches](https://github.com/LIF-Initiative/lif-core/issues/31)

[Issue #32: Query Cache: Implement Write-Optimized Storage and Sync Service](https://github.com/LIF-Initiative/lif-core/issues/32)
