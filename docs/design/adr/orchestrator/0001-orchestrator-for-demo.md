
# ADR 0001: Orchestrator for LIF2 Demo

Date: 2025-07-23

## Status
Accepted

## Context
The LIF framework is supposed to be able to be adapted to use an arbitrary orchestrator (e.g. Dagster, Airflow) that will be used to run tasks to fetch data from data sources both internal to and external to the organization hosting the LIF implementation. These tasks are run when data is not found or is outdated in the LIF Cache.

## Decision
We are deciding to use Dagster as the third party orchestrator in our demo/reference implementation.

### Main Reasons
1. It is a generation newer than Airflow, but is a mature product (founded 2018, 13.6k stars on Github)
2. Dagster offers better documentation for deploying on lots of different platforms. It is also very simple to spin up a dev instance.
3. Dagster offers a SAAS solution that can be utilized from as little as $10 a month, compared to a $300 a month minimum for most Airflow services.

## Alternatives
What other options were considered, and why were they rejected?
### Airflow (2 or 3)
At 41.7k stars on Github, Airflow is one of the widest-known orchestrators. However, we are not initially using Airflow for our demo implementation because:
1. It is a generation older than Dagster
2. It is not as easy to spin up a dev environment as Dagster
3. Dagster has better deployment documentation

### Redis-based Tools (Dramatiq, RQ, Huey, Celery):
We did not choose these tools because:
1. We wanted a robust built-in UI for task visualization and task failure management and diagnosis
2. We did not want in-memory storage for task/job history, at least for this period of initial development.

### AWS SQS + Lambda:
We did not go with this solution because we wanted an option that was cloud agnostic and had an open source offering.

### Prefect:
Given that our workflows are a bit more task-oriented than asset-oriented, Prefect could be a good option. We did not move forward with Prefect because we did not have team members with experience with the tool (unlike Dagster and Airflow).


## Consequences
What are the implications, trade-offs, or side effects of this decision?
1. Having chosen a less widely-implemented tool than Airflow, there may need to be more support provided for getting users up to speed with Dagster.
2. There may be some speed trade-offs compared with the other solutions (particularly against the Redis-based solutions).
3. Our needs are more task-based than asset-based, so we may not be using Dagster's specific strengths to the fullest.


## References
(Optional) Link to related issues, discussions, or documents.
* [Orchestrator Design Doc](https://docs.google.com/document/d/1WBHNVVXl9uegO6AbYt96DC7FjUYcGo9c/edit)
* [Original Linear Issue](https://linear.app/lif/issue/LIF-115/decide-between-dagster-and-airflow)