# Deploying Dagster+ Hybrid on AWS Fargate
At one point LIF utilized the managed version of the Dagster orchestrator, [Dagster+ Hybrid](https://docs.dagster.io/deployment/dagster-plus/hybrid). The Dagster control plane was hosted by Dagster, but actual jobs were run in our own AWS Fargate cluster.

This directory contains AWS Cloud Formation configuration and Github Actions configuration that was used to deploy the Dagster+ Hybrid cloud agent to AWS Fargate. If an organization would like to deploy using Dagster+ hybrid, this could be reincorporated into the Cloud Formation deployment scripts.

When this was originally incorporated, there were service deployments for both a `dev` and `demo` deployment.

This README gives a decent overview of how to deploy for Dagster+ Hybrid on AWS ECR, but is by no means exhaustive. Implementing this will require some iteration to get everything working again. 

## Dagster Cloud Agent
The Dagster Cloud Agent polls Dagster+ for new work and then spins up ECS tasks to execute the work.

The Dockerfile is present in `projects/dagster_plus_hybrid/dagster_cloud_agent`. This was deployed to an AWS ECR repo via a Github action.

### Cloud Formation
The files in this `example_deployment/aws_fargate/cloudformation` file were previously in the main `/cloudformation` directory. To deploy again, they should be moved back to that directory.

#### Additions to `dev.aws` and `demo.aws`
These lines were added in order to use the deployment scripts in this repo to deploy the Dagster Cloud Agent.

```
# dev.aws
STACKS['dev-lif-dagster-cloud-agent']='service'

# As part of STACK_ORDER
dev-lif-dagster-cloud-agent
```

```
# demo.aws
STACKS['demo-lif-dagster-cloud-agent']='service'

# As part of STACK_ORDER
demo-lif-dagster-cloud-agent
```

### AWS Parameter Store Parameters

#### Dagster Access Token
Two parameters were created:
* `/dev/orchestrator/dagster-access-token`
* `/demo/orchestrator/dagster-access-token`

See [here](https://docs.dagster.io/deployment/dagster-plus/management/tokens/agent-tokens) for generating agent tokens.

#### `dagster.yml`
The Cloud Formation template makes use of a parameter store configuration for `dagster.yml`. The following is an example (with fake values) for what this file looked like for the `dev` deployment. The reference for this can be found [here](https://docs.dagster.io/deployment/dagster-plus/hybrid/amazon-ecs/configuration-reference#per-deployment-configuration):
```
dagster_cloud_api:
  url: "<fill in from dagster+>"
  agent_token: "<fill in from dagster+>"
  deployments:
    - prod
  branch_deployments: true

user_code_launcher:
  module: dagster_cloud.workspace.ecs
  class: EcsUserCodeLauncher
  config:
    cluster: dev
    subnets: [<example: subnet-01a1067eeb8a3fa21>]
    service_discovery_namespace_id: <example: ns-pfsr24mf2e4aocpn>
    execution_role_arn: "<example: arn:aws:iam::381492162657:role/dev-lif-dagster-cloud-agent-ECSTaskExecutionRole-o0zHA8Tatu0G>"
    task_role_arn: "<example: arn:aws:iam::381492162657:role/dev-lif-dagster-cloud-agent-ECSTaskExecutionRole-o0zHA8Tatu0G>"
    security_group_ids: [<example: sg-05d7ba3b975ec842c>]
    log_group: dev
    launch_type: "FARGATE"
    requires_healthcheck: true
    code_server_metrics:
      enabled: false
    agent_metrics:
      enabled: false
```

## Dagster Code Location
The code that defined the Dagster jobs was pushed to an AWS ECR repo manually using the AWS CLI. The Dockerfile for this container is in the `projects/dagster_plus_hybrid/Dockerfile.code_location` directory.

The `projects/dagster_plus_hybrid/dagster_cloud.yaml` should be updated with the appropriate AWS ECR repo URL.