#!/usr/bin/env python3
"""
CDK App entry point for the MBA6223 Finance Dashboard infrastructure.

Stacks
------
StorageStack   — DynamoDB table for signal results + S3 bucket for exports
AuthStack      — Cognito User Pool + App Client for mobile auth
ApiStack       — HTTP API Gateway + Lambda handlers for signal endpoints
SchedulerStack — EventBridge Scheduler triggering the morning analysis Lambda
"""
import aws_cdk as cdk

from stacks.storage_stack import StorageStack
from stacks.auth_stack import AuthStack
from stacks.api_stack import ApiStack
from stacks.scheduler_stack import SchedulerStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

storage = StorageStack(app, "FinanceDashboardStorage", env=env)
auth = AuthStack(app, "FinanceDashboardAuth", env=env)
api = ApiStack(
    app,
    "FinanceDashboardApi",
    signals_table=storage.signals_table,
    results_bucket=storage.results_bucket,
    user_pool=auth.user_pool,
    env=env,
)
SchedulerStack(
    app,
    "FinanceDashboardScheduler",
    analysis_function=api.analysis_function,
    env=env,
)

app.synth()
