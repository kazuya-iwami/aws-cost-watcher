# -*- coding: utf-8 -*-
import json
import datetime
import os

import logging
import boto3
import requests
import cfnresponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DAILY_COST_NOTIFICATION_THRESHOLD = int(os.environ['DailyCostNotificationThreshold'])
DAILY_COST_WARNING_THRESHOLD = int(os.environ['DailyCostWarningThreshold'])
SLACK_WEBHOOK_URL = 'https://' + os.environ['SlackWebHookUrl']
LANGUAGE = os.environ['SlackNotificationLanguage']
NOTIFICATION_TIME = int(os.environ['NotificationTime'])

start_str = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
end_str = (datetime.datetime.utcnow() - datetime.timedelta(days=8)).strftime('%Y-%m-%d')
cost_expolerer_url = 'https://console.aws.amazon.com/cost-reports/home?#/custom?groupBy=Service&forecastTimeRangeOption=None&hasBlended=false&excludeRefund=false&excludeCredit=false&excludeRIUpfrontFees=false&excludeRIRecurringCharges=false&excludeOtherSubscriptionCosts=false&excludeSupportCharges=false&excludeTax=false&excludeTaggedResources=false&chartStyle=Stack&timeRangeOption=Last7Days&granularity=Daily&filter=%5B%5D&reportType=CostUsage&hasAmortized=false&startDate={}&endDate={}'.format(start_str, end_str)

time_diff = 0
if LANGUAGE == 'Japanese':
    time_diff = 9

strings = {
    'English': [
        'Daily cost: {}$. Total cost for this month: {}$.',
        'For more information, please see <{}|Cost Explorer>.\n',
        'An error occurred. For more information, please see CloudWatch Logs.',
        '[Cannot get sufficient data] ',
        '🚀 Cost-Watcher was launched. Now, it is performing an operation test. From next time, notifications will be sent at {}:00 if daily cost is over {}$.'
    ],
    'Japanese': [
        '1日で約 {}$ 利用しました. 現在の請求額（今月分）は約 {}$ です. ',
        '詳細は<{}|Cost Explorer>をご覧ください. \n',
        'エラーが発生しました. CloudWatch Logsをご確認下さい. ',
        '[十分なデータが取得できませんでした] ',
        '🚀 Cost-Watcherが起動しました。動作テストを行います。\n次回以降は日本時間{}時に、一日あたりの料金が{}$以上の場合のみ通知を行います。'
    ],
}

account_id = boto3.client('sts').get_caller_identity().get('Account')

def lambda_handler(event, context):
    logger.info('Run.')

    # Process for CFn custom resource
    logger.info(event)
    is_init = False
    try:
        logger.info(event['ResourceProperties']['InitTest'])
        if event['ResourceProperties']['InitTest'] == 'true':
            if event['RequestType'] in ['Create', 'Update']:
                # Run in creating or updating CustomResource
                logger.info('Creating or updating custom resource.')
                is_init = True
                payload = {
                    'username': 'Cost-Watcher@{}'.format(account_id),
                    'icon_emoji': ':money_with_wings:',
                    'text': strings[LANGUAGE][4].format(NOTIFICATION_TIME + time_diff, DAILY_COST_NOTIFICATION_THRESHOLD)
                }
                requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload))
                logger.info('Init message sent successfully.')
            else:
                # Run in deleting CFn stack
                logger.info('Deleting custom resource.')
                cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
                logger.info('Sent CFn response.')
                logger.info('Finish.')
                return
    except Exception as err:
        logger.info(err)


    # main
    try:
        cloud_watch = boto3.client('cloudwatch', region_name='us-east-1')
        # Get service name list
        serevice_names = set()
        response = cloud_watch.list_metrics(
            Namespace='AWS/Billing',
            MetricName='EstimatedCharges',
            Dimensions=[
                {
                    'Name': 'Currency',
                    'Value': 'USD'
                }
            ])
        metrics = response['Metrics']
        for metric in metrics:
            dimensions = metric['Dimensions']
            for dimension in dimensions:
                if dimension['Name'] == 'ServiceName':
                    serevice_names.add(dimension['Value'])

        # Get daily total cost
        response = cloud_watch.get_metric_statistics(
            Namespace='AWS/Billing',
            MetricName='EstimatedCharges',
            Dimensions=[
                {
                    'Name': 'Currency',
                    'Value': 'USD'
                }
            ],
            StartTime=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=8),
            EndTime=datetime.datetime.utcnow(),
            Period=3600*8,
            Statistics=['Maximum']
        )
        datapoints = []
        for datapoint in response['Datapoints']:
            datapoints.append((datapoint['Timestamp'], datapoint['Maximum']))
        datapoints = sorted(datapoints, key=lambda x: x[0], reverse=True)
        daily_charges = 0
        if len(datapoints) > 0:
            for i in range(len(datapoints)-1):
                diff = datapoints[i][1] - datapoints[i+1][1]
                if diff < 0: # Cost is initialized with 0 on 1st of each month.
                    diff = 0
                daily_charges = daily_charges + diff
        else:
            raise RuntimeError('An Error occurred in getting daily total cost. Got no datapoint.')

        if daily_charges < DAILY_COST_NOTIFICATION_THRESHOLD:
            logger.info('Daily cost was less than DAILY_COST_NOTIFICATION_THRESHOLD.')
            return

        charges_until_today = datapoints[0][1]
        
        # Get daily cost of each service.
        service_charges_list = []
        for service_name in serevice_names:
            response = cloud_watch.get_metric_statistics(
                Namespace='AWS/Billing',
                MetricName='EstimatedCharges',
                Dimensions=[
                    {
                        'Name': 'Currency',
                        'Value': 'USD'
                    },
                    {
                        'Name': 'ServiceName',
                        'Value': service_name
                    }
                ],
                StartTime=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=8),
                EndTime=datetime.datetime.utcnow(),
                Period=3600*8,
                Statistics=['Maximum']
            )
            daily_service_charges = 0
            datapoints = []
            
            for datapoint in response['Datapoints']:
                datapoints.append((datapoint['Timestamp'], datapoint['Maximum']))
            datapoints = sorted(datapoints, key=lambda x: x[0], reverse=True)

            if len(datapoints) == 0 or len(datapoints) > 4:
                continue
            if len(datapoints) < 4:
                service_name = strings[LANGUAGE][3] + service_name
            for i in range(len(datapoints)-1):
                diff = datapoints[i][1] - datapoints[i+1][1]
                if diff < 0: # Cost is initialized with 0 on 1st of each month.
                    diff = 0
                daily_service_charges = daily_service_charges + diff
            service_charges_list.append((service_name, daily_service_charges))

        service_charges_list = sorted(
            service_charges_list, key=lambda x: x[1], reverse=True)

        text = strings[LANGUAGE][1].format(cost_expolerer_url)
        for key, val in service_charges_list:
            text += key + ': ' + str(round(val, 2)) + '\n'

        if daily_charges > DAILY_COST_WARNING_THRESHOLD:
            color = 'danger'
        else:
            color = 'good'
        payload = {
            'username': 'Cost-Watcher@{}'.format(account_id),
            'icon_emoji': ':money_with_wings:',
            'text': strings[LANGUAGE][0].format(round(daily_charges, 2), round(charges_until_today, 2)),
            'attachments': [
                {
                    'text': text,
                    'color': color,
                    "mrkdwn_in": ["text"]
                }
            ]
        }
        requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload))
        logger.info('Message sent successfully.')

        if is_init:
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            logger.info('Sent CFn response.')
    
    except Exception as err:
        logger.exception('Error: %s', err)
        payload = {
            'username': 'Cost-Watcher@{}'.format(account_id),
            'icon_emoji': ':money_with_wings:',
            'text': strings[LANGUAGE][2]
        }
        requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload))

    logger.info('Finish.')
