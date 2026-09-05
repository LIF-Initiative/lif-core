# `development/advisor-demo-1org` Directory

This directory contains the developer version of the Docker Compose deployment for the AI Advisor.
This version captures the early demo with only one organization and no orchestration.

Note: the deployment reaches into other directories to build images.

## Usage

To run the demo, starting at the root of the repo:
```
cd development/advisor-demo-1org
docker-compose up --build
docker-compose up --build -d
```

To test, visit: http://localhost:5173/

Shutting the demo down is:
```
docker-compose down -v
```

## Configuration

The query planner reads its information-source list from
`volumes/lif_query_planner/information_sources_config.yml`, mounted read-only at
`/config/` and selected via `LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_PATH`.
It declares the single `org1-example-data-source` source backed by the
`example-data-source-rest-api-to-lif` adapter. Without it the planner falls back
to its built-in default path and comes up with no sources wired.

Fragment paths follow the PascalCase entity convention
(see [`docs/specs/data-model-rules.md`](../../docs/specs/data-model-rules.md)).

## Developer Notes

Developers may want expose services to the host system for direct access and testing.
This can be done by adding a "ports:" section to the service in question.
This may also need adding a "driver: bridge" sub-attribute to the network.

If a component needs access to the host system, add the following the component:
```
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

## Notes
See docker-compose documentation for other usage scenarios.