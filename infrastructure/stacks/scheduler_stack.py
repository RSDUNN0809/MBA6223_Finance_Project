"""
SchedulerStack — EventBridge Scheduler for the morning analysis.

Schedule
--------
Fires at 09:42 AM ET (UTC-4/5 depending on DST) on weekdays only.
  - 09:42 ET = 13:42 UTC during EDT (UTC-4, Mar–Nov)
  - 09:42 ET = 14:42 UTC during EST (UTC-5, Nov–Mar)

To handle DST cleanly we use a UTC cron that fires twice — 13:42 and 14:42 —
and let the Lambda itself check whether the market is actually open before
running the full analysis. This avoids missing a trigger during the DST
transition week.

The 2-minute delay after 09:40 gives Yahoo Finance time to ingest the last
bar of the 10-minute window before the Lambda fetches it.

Dead-letter queue
-----------------
A SQS FIFO queue captures failed invocations so they can be inspected or
replayed manually without losing the morning run.
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_scheduler as scheduler,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_sqs as sqs,
)
from constructs import Construct


class SchedulerStack(cdk.Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        analysis_function: lambda_.Function,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Dead-letter queue for failed invocations ───────────────────────────
        self.dlq = sqs.Queue(
            self,
            "AnalysisDlq",
            queue_name="finance-analysis-dlq.fifo",
            fifo=True,
            content_based_deduplication=True,
            visibility_timeout=cdk.Duration.minutes(15),
            retention_period=cdk.Duration.days(14),
        )

        # ── IAM role for EventBridge Scheduler ────────────────────────────────
        scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            inline_policies={
                "InvokeLambda": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[
                                analysis_function.function_arn,
                                f"{analysis_function.function_arn}:*",
                            ],
                        )
                    ]
                ),
                "SendToDlq": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["sqs:SendMessage"],
                            resources=[self.dlq.queue_arn],
                        )
                    ]
                ),
            },
        )

        # ── EDT schedule: 09:42 ET = 13:42 UTC (Mar–Nov) ──────────────────────
        scheduler.CfnSchedule(
            self,
            "MorningAnalysisEdt",
            name="finance-morning-analysis-edt",
            description="Morning signal analysis at 09:42 ET (EDT window)",
            schedule_expression="cron(42 13 ? * MON-FRI *)",
            schedule_expression_timezone="UTC",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="OFF"
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=analysis_function.function_arn,
                role_arn=scheduler_role.role_arn,
                input='{"source": "scheduler", "timezone": "EDT"}',
                dead_letter_config=scheduler.CfnSchedule.DeadLetterConfigProperty(
                    arn=self.dlq.queue_arn
                ),
                retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                    maximum_retry_attempts=2,
                    maximum_event_age_in_seconds=300,
                ),
            ),
        )

        # ── EST schedule: 09:42 ET = 14:42 UTC (Nov–Mar) ──────────────────────
        scheduler.CfnSchedule(
            self,
            "MorningAnalysisEst",
            name="finance-morning-analysis-est",
            description="Morning signal analysis at 09:42 ET (EST window)",
            schedule_expression="cron(42 14 ? * MON-FRI *)",
            schedule_expression_timezone="UTC",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="OFF"
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=analysis_function.function_arn,
                role_arn=scheduler_role.role_arn,
                input='{"source": "scheduler", "timezone": "EST"}',
                dead_letter_config=scheduler.CfnSchedule.DeadLetterConfigProperty(
                    arn=self.dlq.queue_arn
                ),
                retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                    maximum_retry_attempts=2,
                    maximum_event_age_in_seconds=300,
                ),
            ),
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "AnalysisDlqUrl",
            value=self.dlq.queue_url,
            export_name="FinanceDashboard-AnalysisDlqUrl",
        )
