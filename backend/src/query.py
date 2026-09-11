import json
import boto3
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_NAME', 'SensorReadingsTable')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    try:
        query_params = event.get('queryStringParameters') or {}
        sensor_id = query_params.get('sensor_id')
        
        if not sensor_id:
            return {
                'statusCode': 400, 
                'body': json.dumps({'error': 'Missing query parameter: sensor_id'})
            }
        
        # Query DynamoDB for all readings for the given sensor_id
        response = table.query(
            KeyConditionExpression=Key('sensor_id').eq(sensor_id)
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*' # Required for Person 4's Dashboard
            },
            'body': json.dumps(response.get('Items', []))
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500, 
            'body': json.dumps({'error': 'Internal server error'})
        }
