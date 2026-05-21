
# `deployments/` Directory

This directory contains environment-specific deployment configurations for running the system's composed services in real-world or demonstration environments.

In a Polylith-based architecture, all core logic resides in modular components. However, the way those components are deployed may vary depending on the environment, infrastructure, or demonstration needs. The `deployments/` directory captures these variations, providing reproducible and shareable deployment configurations.

## Purpose

- **Capture actual deployments** for demo instances, cloud environments, or local setups.
- **Define deployment-specific configurations** such as Docker Compose files, infrastructure scripts, cloud provider templates, or env-specific overrides.
- **Serve as a template or reference** for adopters and teams who fork this repository to implement their own deployments.

## Structure Overview

<pre lang="markdown"> <code> 
deployments/  
├── advisor-demo-docker/   # Local docker-compose deployment of the full LIF stack
│ ├── docker-compose.yml
│ ├── information_sources_config*.yml  # per-org orchestrator config
│ └── volumes/                          # per-org query-planner state
</code> </pre>

Today this directory ships one fleshed-out target (`advisor-demo-docker`). Additional deployment targets — alternative cloud providers, customer-specific layouts, or future demos — would go here as sibling directories. AWS deployments for the canonical demo currently live in [`../cloudformation/`](../cloudformation/) and [`../sam/`](../sam/) rather than under `deployments/`.


## Intended Use

- Each subdirectory under `deployments/` corresponds to a **distinct deployment target or instance**.
- Files may include:
  - Dockerfiles
  - `docker-compose.yml`
  - Terraform, CDK, or CloudFormation templates
  - Shell or Python deployment scripts
  - `README.md` files for each target to explain configuration and execution

## For Adopters

If you are forking this repository or adapting it for your own use:
- You are encouraged to create a subdirectory under `deployments/` for your environment.
- This ensures your configurations remain isolated from other deployment targets and can be managed independently.

Example:
<pre lang="markdown"> <code> 
deployments/  
├── your_org_aws_production/  
│ ├── docker-compose.yml  
│ ├── setup.sh  
│ └── README.md
</code></pre>

## Notes

- All configurations in this directory are **environment-specific** and **non-generic**.
- Any logic shared across environments should be extracted into reusable components or scripts.

