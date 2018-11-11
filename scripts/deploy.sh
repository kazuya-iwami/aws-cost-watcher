#!/bin/bash 
# 
# If you want to deploy customized lambda to your environment, use this script.
# 

set -u

echo "Input some parameter."
read -p "1. Webhook URL of Slack (Except 'https://'). You can get the URL from https://slack.com/services/new/incoming-webhook. [hooks.slack.com/services/xxxx]:" SLACK_WEBHOOK_URL
echo "Set slack_webhook_url: ${SLACK_WEBHOOK_URL}"

read -p "2. Language of Slack notification. Now we support English and Japanese. [en / jp]:" LANGUAGE
echo "Set language: ${LANGUAGE}"

read -p "3. Notification time in 24-hour notation (UTC). This value should be 7, 14, 22 because billing metrics are put at around 5(6)am, 1pm, 9pm. [7]:" NOTIFICATION_TIME
echo "Set notification_time: ${NOTIFICATION_TIME}"

read -p "4. Threshold of Daily Cost. Notification color will be red when daily cost is over this threshold (USD). [0]:" DAILY_COST_THRESHOLD
echo "Set : daily_cost_thredhold: ${DAILY_COST_THRESHOLD}"

echo 'Processing...'
ACCOUNT_ID=$(aws sts get-caller-identity | jq -r '.Account')
BUCKET_NAME="cost-watcher-${ACCOUNT_ID}"

pip install -r requirements.txt -t ./function

set -x

# create bucket when it does not exist.
aws s3 ls s3://$BUCKET_NAME || aws s3 mb s3://$BUCKET_NAME

aws cloudformation package --template ../template.yaml \
    --s3-bucket $BUCKET_NAME --output-template-file ../packaged.yaml

aws cloudformation deploy --template-file ../packaged.yaml \
    --stack-name cost-watcher --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides SlackWebHookUrl=$SLACK_WEBHOOK_URL \
    SlackNotificationLangage=$LANGUAGE \
    NotificationTime=$NOTIFICATION_TIME \
    DailyCostThreshold=$DAILY_COST_THRESHOLD

echo 'Finished'