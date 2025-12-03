## Install
### Requirements
1. An AWS account
2. Administrator access to the account via AWS Identity Center
3. A Linux (or Mac) machine with the following packages installed
    * git
    * awscli (v2)
    * bash 4 
4. On the Linux machine, clone this repository and checkout the OW branch
5. Create an AWS CLI profile in .aws/config
    * copy the existing profile as an example
    * choose a new name for the profile
    * set sso_start_url to your organization's AWS Identity Center SSO URL
    * The sso_region is almost always in us-east-1
    * The sso_account_id is the target account for the BMFG LIF stacks
    * The region is the AWS region within the target account for the stacks
6. Create an environment deploy file
    * choose a simple <name> for the new environment (ex. 'prod', 'qa', or 'poc')
    * cp dev.aws <name>.aws
    * edit <name>.aws
        * change all occurrences of 'dev' to '<name>'
        * update AWS_REGION to the target region for the BMGF LIF stacks
        * choose/create an S3 bucket within the target account
        * update TEMPLATE_BUCKET with that bucket name 
        * update SSO_ACCOUNT_NAME with the name of the AWS CLI profile created above
### Steps
7. Create stack parameter files
    * run scripts/init-stack-params.sh helper script
        ```
        scripts/init-stack-params.sh -s <name>
        ```
    * makes a copy of dev param files and updates them according to the provided stack file
    * update the <name>-lif-repositories.params
        * chooose a globally unique S3 bucket name
        * update GitHubRepos
8. Run the deploy script to create the LIF ECR repositories and GitHub Action role
    ```
    ./aws-deploy -s <name> --only-stack <name>-lif-repositories
    ```
    * this must be run by an administrator user
    * the script will initiate an Identity Center SSO login
    * a browser will popup for you to complete your login, and you will be prompted for approval
    * this should be run on your local machine, or in a virtual machine to which you have console access
9. Run the deploy script to deploy all stacks
    ```
    ./aws-deploy -s <name>
    ```

## Notes
### GitHubRepos Parameter
Set GitHubRepos to your GitHub organization and repository pattern (e.g., `myorg/myrepo` or `myorg/*` for all repos) in the <name>-lif-repositories.params file. This value configures the OIDC trust policy for GitHub Actions integration with AWS. If this value is incorrect, your GitHub Actions workflows will fail to run.
**_NOTE:_** If you run multiple LIF environment stacks in a single account, you can create only one OIDC provider per account.  Thus you should set the ExistingProviderArn to the ARN of the existing provider.

### Target Group Targeting (Public Services Only)
The service.yml template supports three methods for routing traffic to target groups:
- **Path-based**: Set `PathPattern` parameter (e.g., `/api/*`) to route requests matching specific URL paths
- **Domain-based**: Set `DomainNames` parameter (comma-delimited list) to route requests from specific hostnames
- **HTTP header-based**: When both path and domain are specified as 'notapplicable', the template will create a routing rule in the load balancer based on a `TargetGroup` HTTP header matching the target group name, which takes the format "${EnvironmentName}-${ServiceName}".

### Public Services
The service.yml template supports making services public. To make a service public:

1. Set `UseLbForService = true`
2. Set `DomainNames` or `PathPattern` (for dev/demo use DomainNames)
    * Example: `advisor.lif.unicon.net`
    * Must be within the domain for the given env (dev - `?.lif.unicon.net`, demo - `?.demo.lif.unicon.net`)
3. Set `Priority`
    * Must be a unique integer for the given env with respect to other public services
    * Look at other param files for public services (UseLbForService = true) for the env:
    ```
    jq -r '.[] | select(.ParameterKey == "Priority") | .ParameterValue' cloudformation/dev-lif-*.params | sort -u
    ```
4. Set `HealthCheckUrl`
    * The selected URL must support HTTP GET and return an HTTP 200 code
    * Ideally, the payload will be small

### Cognito Authorization
To enable Cognito authentication for a public service:

1. Set `EnableCognitoAuth = true` (requires domain-based targeting)
2. Deploy the service stack - this creates a Cognito User Pool named `${EnvironmentName}-${ServiceName}-access`
3. Admin must manually create users in the User Pool:
    * Navigate to AWS Cognito console
    * Find the User Pool (named `${EnvironmentName}-${ServiceName}-access`)
    * Create users with email addresses as usernames
    * Users will receive temporary passwords via email and must change them on first login

### TaskDef Overrides
Customize ECS task definitions using taskdef include files:

1. Create a `<service-name>-taskdef-includes.yml` file in the cloudformation directory
2. Set the `TaskDefIncludesFile` parameter to the S3 URL of your include file
3. The include file can contain:
    * `Environment`: Array of environment variables for the container
    * `Secrets`: Array of secrets from SSM Parameter Store or Secrets Manager
4. Example structure:
    ```yaml
    Environment:
      - Name: LOG_LEVEL
        Value: DEBUG
    Secrets:
      - Name: API_KEY
        ValueFrom: arn:aws:secretsmanager:region:account:secret:name
    ```

### TaskRole Overrides
Customize ECS task execution role permissions using taskrole include files:

1. Create a `<service-name>-taskrole-includes.yml` file in the cloudformation directory
2. Set the `TaskRoleIncludesFile` parameter to the S3 URL of your include file
3. The include file contains additional IAM policies to attach to the task execution role
4. Example structure:
    ```yaml
    Policies:
      - PolicyName: CustomPolicy
        PolicyDocument:
          Statement:
          - Effect: Allow
            Action:
              - 's3:GetObject'
              - 'secretsmanager:GetSecretValue'
            Resource:
              - 'arn:aws:s3:::my-bucket/*'
              - 'arn:aws:secretsmanager:*:*:secret:my-secret*'
    ```

### EFS Shared Storage
All services deployed with service.yml automatically get access to shared EFS storage:

- Default mount point: `/mnt/efs` inside the container
- Each service gets its own subdirectory: `/${ServiceName}`
- Mount location can be customized using taskdef overrides by adding `MountPoints` configuration
- Useful for sharing files between services or persisting data across container restarts

### CloudMap Service Discovery
All services are automatically registered with AWS CloudMap for internal service discovery:

- CloudMap provides DNS-based service discovery for backend services within the VPC
- Services can communicate using simple hostnames: `http://{ServiceName}.lif.{EnvironmentName}.aws:{ContainerPort}`
- Example: `http://graphql-org1.lif.webdev.aws:8000/graphql`
- Eliminates need for hardcoded IP addresses or load balancer endpoints for internal communication
- Automatically handles service registration/deregistration as containers start/stop

### Container CPU and Memory
Set appropriate CPU and memory values for your containers:

- `ContainerCpu`: CPU units (1024 = 1 vCPU)
- `ContainerMemory`: Memory in MB
- For Fargate, CPU and memory must be valid combinations
- See [AWS Fargate task size documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html#fargate-tasks-size) for supported combinations
- Start with smaller values and scale up based on monitoring data
