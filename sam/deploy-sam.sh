#!/bin/bash -eu

#title           :deploy
#description     :This script AWS resources
#author          :Alex Bragg, Unicon, Inc.
#date            :FEB-2022
#version         :0.1

export ARGS=$@
export PATH=$PATH:/usr/local/bin
export AWS_DEFAULT_OUTPUT="json"
export TRACING_ENABLED=false
export DATE_TAG=$(date +%F_%H-%M-%S)

set -o pipefail

main() {
  getOptions ${ARGS[*]}
  checkDependencies
  cd $SAM_DIR
  buildDockerImages
  samBuild
  samDeploy
}

die () {
  echo -e >&2 "\n$@\n"
  exit 1
}

printGreen() {
  GREEN='\033[0;32m'
  NC='\033[0m'
  printf >&2 "${GREEN}$@${NC}\n"
}

getOptions() {
  while [[ $# -gt 0 ]]; do
    key="$1"

    case $key in
      -s|--stack-file)
        export STACK_FILE=$2
        shift
        ;;
      -d|--sam-dir)
        export SAM_DIR=$2
        shift
        ;;
      -h|--help)
        printUsage
        exit 0
        ;;
      -v|--verbose)
        set -x
        export VERBOSE="-v"
        export TRACING_ENABLED=true
        ;;
      *)
        printUsage
        die "Invalid option: $key"
        ;;
    esac
    shift
  done

  if [ "foo" = "${STACK_FILE:=foo}" ]; then
    printUsage
  fi

  if [ "foo" = "${SAM_DIR:=foo}" ]; then
    printUsage
  fi

  if [ ! -f "${STACK_FILE}.aws" ]; then
    printUsage
    die "Stacks and basic settings for the target environment ${STACK_FILE}.aws"
  else
    source "${STACK_FILE}.aws"
#    export AWS_PROFILE=$SSO_ACCOUNT_NAME
    export CONFIG_ENV=$SAM_CONFIG_ENV
    export AWS_DEFAULT_REGION=$AWS_REGION
  fi

  if [ ! -d "${SAM_DIR}" ]; then
    die "Did not find ${SAM_DIR}"
  fi
}

printUsage() {
cat << EOF

This script creates or updates AWS resources

usage: $0 -s stack-file [-h][-v]
  options:
    -s, --stack-file      The stack file name prefix (minus .aws extension)
                            (ex. dev or qa)
    -d, --sam-dir         The directory containing the SAM application
    -v, --verbose         Enable debug output
    -h, --help            prints this usage

EOF
}

checkDependencies() {
  which aws 2>&1 > /dev/null || die "This script requires the AWS CLI tools installed"
  which docker 2>&1 > /dev/null || die "This script requires docker installed"
  which yq 2>&1 > /dev/null || die "This script requires yq installed (https://github.com/mikefarah/yq)"
  which sam 2>&1 > /dev/null || die "This script requires AWS SAM installed (https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)"
}

buildDockerImages() {
  ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
  . ${SAM_CONFIG_ENV}.dockerImages
  for image in "${!DOCKER_IMAGES[@]}"; do 
    cd ${DOCKER_IMAGES[$image]}
    REPOSITORY=$image
    REGISTRY=${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com

    # create the repository to push to
    printGreen "Check/create ECR repo: ${REPOSITORY}"
    repoExists=$(aws ecr describe-repositories --repository-name ${REPOSITORY} 2>&1) || aws ecr create-repository --repository-name ${REPOSITORY} --image-scanning-configuration scanOnPush=true

    aws ecr get-login-password | docker login --username AWS --password-stdin ${REGISTRY}
    printGreen "building Docker image: $REGISTRY/$REPOSITORY:latest"
    docker build . -t $REGISTRY/$REPOSITORY:latest
    docker push $REGISTRY/$REPOSITORY:latest
    docker tag $REGISTRY/$REPOSITORY:latest $REGISTRY/$REPOSITORY:$DATE_TAG
    docker push $REGISTRY/$REPOSITORY:$DATE_TAG 
    cd -
  done
}

samBuild() {
  sam build
}

samDeploy() {
  CONFIG_VARS=$(cat samconfig.yaml | yq ".${SAM_CONFIG_ENV}.deploy.parameters.parameter_overrides" | tr -d '"')
  sam deploy --config-env $SAM_CONFIG_ENV --parameter-overrides "$CONFIG_VARS pImageTag=$DATE_TAG"
}

main
