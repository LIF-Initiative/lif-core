
# `projects/` Directory

This directory defines executable Python projects that combine Polylith components and bases into runnable services. Each subdirectory under `projects/` represents a self-contained application — typically packaged as a Docker image — that can be deployed in various environments.

## Purpose

Projects are responsible for:
- Composing a base with required components into an executable program
- Building and packaging the result (e.g., into a Docker image)
- Maintaining generic executables that can be reused across deployments with configuration alone

These directories correspond to typical Python project structures, including a `pyproject.toml` file for dependency and build configuration.

## Key Characteristics

- Each project is a Polylith "project" brick.
- Projects are generic: they don’t hard-code environment-specific behavior.
- Configuration is expected to be provided externally — via environment variables, config files, or deployment systems.
- If a LIF service supports multiple variations (e.g., feature sets), there may be more than one project associated with that service.

## Example Structure

<pre lang="markdown"> <code> 
projects/  
├── lif_query_cache_api/  
│ ├── pyproject.toml # Project metadata and dependencies  
│ ├── Dockerfile # Container build instructions  
│ ├── build.sh # Local build script  
│ └── build-docker.sh # Build Docker image  
│  
├── lif_graphql_api/  
│ └── ...  
│  
├── lif_query_planner_api/  
│ └── ...
</code> </pre>

### Each project includes:
- A `pyproject.toml` defining the Python package and build context
- Shell scripts for building the app or Docker image
- A Dockerfile describing how to package the service

## Usage

To build a project locally:

    cd projects/lif_query_cache_api
    bash build.sh

To build the Docker image:

    bash build-docker.sh


## Guidelines

-   Projects should not include business logic — that belongs in components.
-   Shared functionality across projects should be factored into components or base modules.
-   Keep each project clean, self-contained, and independently testable.
-   Ensure the executable behavior remains environment-agnostic.

## Related Directories

-   `components/`: Defines reusable logic
-   `bases/`: Wraps components with deployment context (e.g. API or CLI)   
-   `deployments/`: Provides environment-specific configuration and scripts
-   `development/`: Supports local development and tooling
