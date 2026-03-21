"""
ApiStack — HTTP API Gateway v2 + Lambda functions.

Endpoints
---------
GET  /signals              — latest BUY/SELL/HOLD results (from DynamoDB)
GET  /signals/{ticker}     — history for a single ticker (ByTicker GSI)
GET  /signals/export       — presigned S3 URL for CSV download
POST /signals/refresh      — trigger on-demand analysis run (admin only)

All endpoints are protected by a Cognito JWT authorizer.

Lambda functions
----------------
signal_handler   — serves GET /signals endpoints
analysis_function — runs the full S&P 500 morning analysis (also used by
                    the scheduler).  Writes results to DynamoDB + S3.

Lambda Layer
------------
A shared layer packages the heavy Python dependencies (pandas, numpy,
yfinance, pytz, requests, lxml) to keep deployment packages small.
The src/ package from the project root is also bundled into the layer so
both Lambdas share the same signal/data logic without duplication.
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_authorizers as authorizers,
    aws_apigatewayv2_integrations as integrations,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct
import os


class ApiStack(cdk.Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        signals_table: dynamodb.Table,
        results_bucket: s3.Bucket,
        user_pool: cognito.UserPool,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        layer_path = os.path.join(os.path.dirname(__file__), "..", "lambda", "layer")

        # ── Shared Lambda Layer ────────────────────────────────────────────────
        # Contains: pandas, numpy, yfinance, pytz, requests, lxml, scikit-learn
        # and the project's src/ package.
        # Build with: pip install -r lambda/layer/requirements.txt \
        #               -t infrastructure/lambda/layer/python/lib/python3.11/site-packages
        finance_layer = lambda_.LayerVersion(
            self,
            "FinanceDepsLayer",
            layer_version_name="finance-dashboard-deps",
            code=lambda_.Code.from_asset(layer_path),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            compatible_architectures=[lambda_.Architecture.ARM_64],
            description="pandas, numpy, yfinance, pytz, lxml, scikit-learn + src/",
        )

        # ── Shared environment variables ───────────────────────────────────────
        shared_env = {
            "SIGNALS_TABLE_NAME": signals_table.table_name,
            "RESULTS_BUCKET_NAME": results_bucket.bucket_name,
            "SIGNAL_TTL_DAYS": "30",
            "LOG_LEVEL": "INFO",
        }

        # ── IAM role for Lambda functions ──────────────────────────────────────
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        signals_table.grant_read_write_data(lambda_role)
        results_bucket.grant_read_write(lambda_role)

        # ── Signal handler Lambda (serves GET requests) ────────────────────────
        self.signal_handler = lambda_.Function(
            self,
            "SignalHandler",
            function_name="finance-dashboard-signal-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda", "signal_handler")
            ),
            layers=[finance_layer],
            role=lambda_role,
            environment=shared_env,
            timeout=cdk.Duration.seconds(30),
            memory_size=512,
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # ── Analysis Lambda (full S&P 500 run — slow, used by scheduler too) ───
        self.analysis_function = lambda_.Function(
            self,
            "AnalysisFunction",
            function_name="finance-dashboard-analysis",
            runtime=lambda_.Runtime.PYTHON_3_11,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda", "scheduler_handler")
            ),
            layers=[finance_layer],
            role=lambda_role,
            environment=shared_env,
            # Full S&P 500 analysis can take several minutes
            timeout=cdk.Duration.minutes(10),
            memory_size=1024,
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )

        # ── HTTP API Gateway ───────────────────────────────────────────────────
        self.http_api = apigwv2.HttpApi(
            self,
            "FinanceDashboardApi",
            api_name="finance-dashboard-api",
            description="Morning Trading Signal Dashboard — mobile API",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_headers=["Authorization", "Content-Type"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_origins=["*"],  # tighten to app domain in production
                max_age=cdk.Duration.hours(1),
            ),
        )

        # ── Cognito JWT Authorizer ─────────────────────────────────────────────
        jwt_authorizer = authorizers.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[],   # populated at deploy time via context or env
            authorizer_name="CognitoJwtAuthorizer",
            identity_source=["$request.header.Authorization"],
        )

        signal_integration = integrations.HttpLambdaIntegration(
            "SignalIntegration", self.signal_handler
        )
        analysis_integration = integrations.HttpLambdaIntegration(
            "AnalysisIntegration", self.analysis_function
        )

        # ── Routes ─────────────────────────────────────────────────────────────
        self.http_api.add_routes(
            path="/signals",
            methods=[apigwv2.HttpMethod.GET],
            integration=signal_integration,
            authorizer=jwt_authorizer,
        )
        self.http_api.add_routes(
            path="/signals/{ticker}",
            methods=[apigwv2.HttpMethod.GET],
            integration=signal_integration,
            authorizer=jwt_authorizer,
        )
        self.http_api.add_routes(
            path="/signals/export",
            methods=[apigwv2.HttpMethod.GET],
            integration=signal_integration,
            authorizer=jwt_authorizer,
        )
        self.http_api.add_routes(
            path="/signals/refresh",
            methods=[apigwv2.HttpMethod.POST],
            integration=analysis_integration,
            authorizer=jwt_authorizer,
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "ApiEndpoint",
            value=self.http_api.api_endpoint,
            export_name="FinanceDashboard-ApiEndpoint",
        )
        cdk.CfnOutput(
            self,
            "SignalHandlerArn",
            value=self.signal_handler.function_arn,
            export_name="FinanceDashboard-SignalHandlerArn",
        )
        cdk.CfnOutput(
            self,
            "AnalysisFunctionArn",
            value=self.analysis_function.function_arn,
            export_name="FinanceDashboard-AnalysisFunctionArn",
        )
