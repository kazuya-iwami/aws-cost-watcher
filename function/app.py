# -*- coding: utf-8 -*-
import json
import datetime
import os

import logging
import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DAILY_CHARGES_THRESHOLD = int(os.environ['DailyChargesThreshold'])
SLACK_WEBHOOK_URL = 'https://' + os.environ['SlackWebHookUrl']

def lambda_handler(event, context):
    """Cost Watcher
    無料使用枠に収まる範囲でコストを集計する
    CWのEstimatedChargesは、UTC5:00, 13:00, 21:00頃にputされるので、このコードでは今日、昨日のUTC5:00の差分額を利用する
    Lambdaは日本時間の16時(UTC7:00)に発火させる
    通知内容は、1日分の合計及びサービスごとの請求金額
    初使用のサービスは約1日後から計測対象
    """

    try:
        cloud_watch = boto3.client('cloudwatch', region_name='us-east-1')
        
        # サービス名取得
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

        # 1日分の請求額取得
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
        if len(datapoints) != 4:
            raise RuntimeError('len(datapoints) should be 4')
        datapoints = sorted(datapoints, key=lambda x: x[0], reverse=True)
        if datetime.datetime.utcnow().day == 1:
            # 各月1日に値が0初期化され、初回のdatapointは金額が0になるため、前日のdatapointsから金額を推定
            daily_charges = (datapoints[2][1] - datapoints[0][1]) * 3 / 2.0
        else:
            daily_charges = datapoints[0][1] - datapoints[3][1]

        charges_until_today = datapoints[0][1]

        # 1日分のサービスごとの請求額
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
            datapoints = []
            for datapoint in response['Datapoints']:
                datapoints.append((datapoint['Timestamp'], datapoint['Maximum']))
            if len(datapoints) != 4:
                logger.warn('{}: len(datapoints) should be 4'.format(service_name))
                continue
            datapoints = sorted(datapoints, key=lambda x: x[0], reverse=True)
            if datetime.datetime.utcnow().day == 1:
                # 各月1日に値が0初期化され、初回のdatapointは金額が0になるため、前日のdatapointsから金額を推定
                daily_service_charges = (datapoints[0][1] - datapoints[2][1]) * 3 / 2.0
            else:
                daily_service_charges = datapoints[0][1] - datapoints[3][1]
            service_charges_list.append((service_name, daily_service_charges))

        service_charges_list = sorted(
            service_charges_list, key=lambda x: x[1], reverse=True)

        text = ''
        for key, val in service_charges_list:
            text += key + ': ' + str(round(val, 2)) + '\n'

        if daily_charges > DAILY_CHARGES_THRESHOLD:
            color = 'danger'
        else:
            color = 'good'

        payload = {
            'username': 'Cost-Watcher',
            'icon_emoji': ':money_with_wings:',
            'attachments': [
                {
                    'title': '1日で約 {}$分利用しました\n現在の今月の合計請求額は {}$です'.format(round(daily_charges, 2), round(charges_until_today, 2)),
                    'text': text,
                    'color': color
                }
            ]
        }
        requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload))
    
    except Exception as err:
        logger.exception('Error: %s', err)
        payload = {
            'username': 'Cost-Watcher',
            'icon_emoji': ':money_with_wings:',
            'attachments': [
                {
                    'title': 'エラーが発生しました。CloudWatch Logsを確認下さい',
                    'color': 'danger'
                }
            ]
        }
        requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload))

lambda_handler(None, None)
