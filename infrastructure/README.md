# Finance Dashboard — AWS Infrastructure

AWS CDK v2 (Python) infrastructure for the MBA6223 Morning Signal Dashboard mobile API.

## Architecture

```
Mobile App (iOS / Android / React Native)
         │
         ▼
  API Gateway HTTP API  ──── Cognito JWT Authorizer
         │
    ┌────┴─────────────────────────┐
    │                              │
    ▼                              ▼
SignalHandler Lambda        AnalysisFunction Lambda
(GET /signals*)             (POST /signals/refresh)
    │                              │  ▲
    ▼                              │  │
DynamoDB                     EventBridge Scheduler
SignalResults                (09:42 AM ET, weekdays)
    │
    ▼
  S3 Bucket
(CSV exports)
```

## Stacks

| Stack | Resources |
|-------|-----------|
| `FinanceDashboardStorage` | DynamoDB `SignalResults` table + S3 export bucket |
| `FinanceDashboardAuth` | Cognito User Pool + mobile App Client |
| `FinanceDashboardApi` | HTTP API Gateway + Lambda Layer + 2 Lambda functions |
| `FinanceDashboardScheduler` | EventBridge Scheduler (EDT + EST triggers) + DLQ |

## Prerequisites

- Python 3.11+
- Node.js (for CDK CLI): `npm install -g aws-cdk`
- AWS CLI configured: `aws configure`
- AWS account bootstrapped: `cdk bootstrap aws://ACCOUNT/REGION`

## Deploy

```bash
cd infrastructure

# Install CDK Python dependencies
pip install -r requirements.txt

# Build the Lambda Layer (downloads ARM64 wheels + copies src/)
make layer

# Preview changes
make diff

# Deploy all stacks
make deploy
```

## API Endpoints

All endpoints require a valid Cognito JWT in the `Authorization` header.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/signals` | Latest BUY/SELL/HOLD results (today by default; `?date=YYYY-MM-DD`) |
| `GET` | `/signals/{ticker}` | Last 30 days of signals for one ticker |
| `GET` | `/signals/export` | Presigned S3 URL for CSV download |
| `POST` | `/signals/refresh` | Trigger an on-demand analysis run |

## Mobile Auth Flow

1. Use AWS Amplify or a Cognito SDK in the mobile app
2. Sign-in with SRP (`USER_SRP_AUTH`) — no client secret required
3. Include the ID token as `Authorization: Bearer <token>` on API calls
4. Tokens expire after 1 hour; refresh token valid for 30 days

## DynamoDB Schema

**Table**: `SignalResults`
**PK**: `run_date` (String) — `"YYYY-MM-DD"`
**SK**: `ticker` (String) — e.g. `"AAPL"`
**TTL**: `expires_at` — records auto-deleted after 30 days

**GSI: BySignal** — query all tickers with a given signal
**GSI: ByTicker** — query signal history for one ticker

## Cost Estimate (approximate, us-east-1)

| Service | Est. monthly cost |
|---------|-------------------|
| Lambda (2 fns, ~22 invocations/month) | ~$0.00 (free tier) |
| DynamoDB (on-demand, ~500 writes/day) | ~$0.50 |
| S3 (CSV exports, ~22 files/month) | ~$0.01 |
| API Gateway HTTP API (low traffic) | ~$0.01 |
| Cognito (≤ 50 MAU) | $0.00 (free tier) |
| EventBridge Scheduler | $0.00 (free tier) |
| **Total** | **< $1/month** |
