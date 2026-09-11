# Person 2: AWS Backend 

This folder contains the Serverless backend required for the Synthesized Sensor Data Project. It uses the AWS Serverless Application Model (SAM) to deploy two API Gateway endpoints, two Lambda functions, and a DynamoDB table.

## Deployment Instructions

### Prerequisites
1. Ensure you have followed the **AWS Free Tier Setup & Safety Guide** to create and secure your AWS account.
2. Install the [AWS CLI](https://aws.amazon.com/cli/) and configure it using `aws configure`.
3. Install the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).

### Deploying the Stack
Run the following commands inside this `backend/` directory:

1. **Build the application:**
   ```bash
   sam build
   ```

2. **Deploy to AWS:**
   ```bash
   sam deploy --guided
   ```
   - **Stack Name**: `sensor-data-backend`
   - **AWS Region**: Hit enter for your default region (e.g., `us-east-1`)
   - **Confirm changes before deploy**: `y`
   - **Allow SAM CLI IAM role creation**: `y`
   - **Disable authorization for APIs**: `y` (This will allow Person 3 & 4 to access the API without setting up IAM auth yet)
   - Save arguments to configuration file: `y`

After the deployment completes, SAM will print the `ApiEndpoint` URL in the outputs. **Copy this URL**.

---

## API Endpoints Hand-off (For Person 3 & Person 4)

Once deployed, provide the following details to Person 3 (Simulator) and Person 4 (Dashboard):

**Base API URL:** `https://<YOUR-API-ID>.execute-api.<REGION>.amazonaws.com/Prod`

### 1. Ingest Reading (Person 3)
- **Method:** `POST`
- **Path:** `/readings`
- **Body:** JSON object containing at least `sensor_id` and `timestamp`.

**Test with cURL:**
```bash
curl -X POST https://<YOUR-API-ID>.execute-api.<REGION>.amazonaws.com/Prod/readings \
     -H "Content-Type: application/json" \
     -d '{"sensor_id": "ROOM_101_TEMP", "timestamp": "2023-10-23T08:00:00Z", "value": 22.5}'
```

### 2. Query Readings (Person 4)
- **Method:** `GET`
- **Path:** `/readings?sensor_id=<SENSOR_ID>`

**Test with cURL:**
```bash
curl -X GET "https://<YOUR-API-ID>.execute-api.<REGION>.amazonaws.com/Prod/readings?sensor_id=ROOM_101_TEMP"
```
