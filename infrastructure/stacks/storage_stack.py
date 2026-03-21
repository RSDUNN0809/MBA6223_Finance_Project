"""
StorageStack — DynamoDB table for signal results + S3 bucket for CSV exports.

DynamoDB schema
---------------
Table:  SignalResults
PK:     run_date      (String)  — "YYYY-MM-DD"
SK:     ticker        (String)  — e.g. "AAPL"
Attrs:  signal, score, votes (JSON), details (JSON), computed_at (ISO-8601)
TTL:    expires_at            — records auto-deleted after 30 days

GSI:    BySignal
  PK:   signal  (String)  — "BUY" | "SELL" | "HOLD"
  SK:   score   (Number)  — enables range queries on score within a signal type

S3 bucket
---------
- signal-results-exports/YYYY-MM-DD/signals.csv
- Versioning enabled; lifecycle rule moves objects to IA after 30 days
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    RemovalPolicy,
)
from constructs import Construct


class StorageStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── DynamoDB: SignalResults ────────────────────────────────────────────
        self.signals_table = dynamodb.Table(
            self,
            "SignalResultsTable",
            table_name="SignalResults",
            partition_key=dynamodb.Attribute(
                name="run_date", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="ticker", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

        # GSI: query all tickers with a given signal for a date
        self.signals_table.add_global_secondary_index(
            index_name="BySignal",
            partition_key=dynamodb.Attribute(
                name="signal", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="score", type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # GSI: query all results for a specific ticker across dates
        self.signals_table.add_global_secondary_index(
            index_name="ByTicker",
            partition_key=dynamodb.Attribute(
                name="ticker", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="run_date", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── S3: Signal Exports ─────────────────────────────────────────────────
        self.results_bucket = s3.Bucket(
            self,
            "SignalExportsBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="MoveToIA",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=cdk.Duration.days(30),
                        )
                    ],
                ),
                s3.LifecycleRule(
                    id="ExpireOldVersions",
                    enabled=True,
                    noncurrent_version_expiration=cdk.Duration.days(90),
                ),
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET],
                    allowed_origins=["*"],  # tighten to app domain in production
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "SignalResultsTableName",
            value=self.signals_table.table_name,
            export_name="FinanceDashboard-SignalResultsTableName",
        )
        cdk.CfnOutput(
            self,
            "SignalExportsBucketName",
            value=self.results_bucket.bucket_name,
            export_name="FinanceDashboard-SignalExportsBucketName",
        )
