#!/usr/bin/env bash
DEST_BUCKET='cmdb-automation'
TEMPLATE_FILE='tags-aws-config.yaml'
PARAM_FILE='tgs-aws-config-parameters.json'
STACK_NAME='TagsAutomation'
if [ -z "$1" ]
  then
    echo "No destination bucket provided. setting the bucket to: " $DEST_BUCKET
  else
    echo "Setting the destination to: " $1
    DEST_BUCKET=$1
fi

if [ ! -d "output" ]
  then
  echo "Creating output directory"
  mkdir output
fi

echo 'Building the template stack'
aws cloudformation package \
    --template-file templates/${TEMPLATE_FILE} \
    --s3-bucket $DEST_BUCKET \
    --output-template-file output/${TEMPLATE_FILE} \
#    --profile=prod2-account

echo 'Deploying the stack'
aws cloudformation deploy \
    --template-file output/${TEMPLATE_FILE} \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
    $(jq -r '.Parameters | keys[] as $k | "\($k)=\(.[$k])"' parameters/${PARAM_FILE}) \
    --stack-name ${STACK_NAME} \
#    --profile=prod2-account

