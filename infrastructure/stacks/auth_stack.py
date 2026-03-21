"""
AuthStack — Cognito User Pool + App Client for mobile authentication.

Design
------
- User Pool with email sign-in and MFA optional
- App Client configured for the mobile app (no client secret — required for
  native mobile apps that cannot securely store a secret)
- Token validity: ID/access 1 hour, refresh 30 days
- Password policy enforces complexity suitable for financial data access
"""
import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class AuthStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── User Pool ──────────────────────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self,
            "FinanceDashboardUserPool",
            user_pool_name="finance-dashboard-users",
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            self_sign_up_enabled=False,   # invite-only; admin creates accounts
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=cdk.Duration.days(7),
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                given_name=cognito.StandardAttribute(required=False, mutable=True),
                family_name=cognito.StandardAttribute(required=False, mutable=True),
            ),
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ── Mobile App Client ──────────────────────────────────────────────────
        # No client secret — mobile apps (iOS/Android) cannot store it securely.
        # Uses PKCE flow (Proof Key for Code Exchange) instead.
        self.app_client = self.user_pool.add_client(
            "MobileAppClient",
            user_pool_client_name="finance-dashboard-mobile",
            generate_secret=False,   # required for public clients (mobile/SPA)
            auth_flows=cognito.AuthFlow(
                user_srp=True,         # secure remote password — recommended
                user_password=False,   # disabled; less secure
                admin_user_password=False,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,  # PKCE
                    implicit_code_grant=False,
                ),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                # Update callback/logout URLs to match your mobile app's
                # registered deep-link scheme (e.g. financedashboard://auth)
                callback_urls=["financedashboard://auth/callback"],
                logout_urls=["financedashboard://auth/logout"],
            ),
            access_token_validity=cdk.Duration.hours(1),
            id_token_validity=cdk.Duration.hours(1),
            refresh_token_validity=cdk.Duration.days(30),
            prevent_user_existence_errors=True,
        )

        # ── Hosted UI Domain ───────────────────────────────────────────────────
        self.user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix="finance-dashboard-mba6223"
            ),
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            export_name="FinanceDashboard-UserPoolId",
        )
        cdk.CfnOutput(
            self,
            "UserPoolClientId",
            value=self.app_client.user_pool_client_id,
            export_name="FinanceDashboard-UserPoolClientId",
        )
        cdk.CfnOutput(
            self,
            "CognitoHostedUiDomain",
            value=f"https://finance-dashboard-mba6223.auth.{self.region}.amazoncognito.com",
            export_name="FinanceDashboard-CognitoHostedUiDomain",
        )
