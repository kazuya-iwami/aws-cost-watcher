#!/bin/bash 
set -u

pip install -r requirements.txt -t ./function

ACCOUNT_ID=$(aws sts get-caller-identity | jq -r '.Account')
BUCKET_NAME="cost-watcher-${ACCOUNT_ID}"

# Add some parameters to "AWS Systems Manager Parameter Store"
echo "Setting some paramter..."
read -p "daily_charges_threshold($): Notification color will be red when daily cost is over this threshold: " THRESHOLD
echo "Set daily_charges_threshold($): ${THRESHOLD}"
aws ssm put-parameter --name /cost_watcher/daily_charges_threshold --value $THRESHOLD --type String --overwrite

read -p "slack_webhook_url (except 'https://'): " URL
echo "Set slack_webhook_url: ${URL}"
aws ssm put-parameter --name /cost_watcher/encrypted_slack_webhook_url --value $URL --type SecureString --overwrite

set -x

# create bucket when it does not exist.
aws s3 ls s3://$BUCKET_NAME || aws s3 mb s3://$BUCKET_NAME

aws cloudformation package --s3-bucket $BUCKET_NAME \
     --template-file template.yaml --output-template-file packaged.yaml

aws cloudformation deploy --template-file packaged.yaml \
    --stack-name cost-watcher --capabilities CAPABILITY_NAMED_IAM