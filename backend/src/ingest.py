import json
import boto3
import os
import decimal

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_NAME', 'SensorReadingsTable')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    try:
        # Check if the body exists
        if not event.get('body'):
            return {
                'statusCode': 400, 
                'headers': {
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Missing request body'})
            }
            
        body = json.loads(event['body'], parse_float=decimal.Decimal)
        
        # Validate required fields
        if 'sensor_id' not in body or 'timestamp' not in body:
            return {
                'statusCode': 400, 
                'headers': {
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Missing required fields: sensor_id and timestamp'})
            }
        
        # Write to DynamoDB
        table.put_item(Item=body)
        
        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*' # Required for Person 4's Dashboard
            },
            'body': json.dumps({'message': 'Reading ingested successfully'})
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500, 
            'headers': {
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }
