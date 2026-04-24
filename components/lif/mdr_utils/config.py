from functools import cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # CORS configuration
    cors_allow_origins: str = "*"  # comma-separated list of allowed origins
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS,PATCH"
    cors_allow_headers: str = "*"
    # Authentication configuration
    mdr__auth__jwt_secret_key: str = "changeme4"
    mdr__auth__access_token_expire_minutes: int = 30
    mdr__auth__refresh_token_expire_days: int = 7
    mdr__auth__methods_to_require_auth: str = "GET,POST,PUT,DELETE"
    mdr__auth__service_api_key__graphql: str = "changeme1"
    mdr__auth__service_api_key__semantic_search: str = "changeme2"
    mdr__auth__service_api_key__translator: str = "changeme3"
    # Used by the Cognito post-confirmation Lambda to call POST /tenants/provision
    # when a new user registers (issue #883 PR 4b).
    mdr__auth__service_api_key__post_confirm: str = "changeme5"
    mdr__auth__public_allowlist_exact: str = "/login,/refresh-token,/health-check"
    mdr__auth__public_allowlist_starts_with: str = "/docs,/openapi.json"
    # Cognito configuration (empty user_pool_id = Cognito auth disabled)
    mdr__auth__cognito_user_pool_id: str = ""
    mdr__auth__cognito_region: str = "us-east-1"
    mdr__auth__cognito_spa_client_id: str = ""
    # Tenant routing (issue #883). When enabled, every DB session runs SET
    # search_path to a tenant_* schema derived from the caller's Cognito
    # group. Default off — flipped on in each env after the one-time public
    # → tenant_lif_team data migration (PR 3 of the #883 split).
    mdr__tenant_routing__enabled: bool = False
    # Schema for API-key callers (services) and any Cognito user without a
    # group. Stays "public" until the PR 3 cutover sets this to
    # "tenant_lif_team" in env params.
    mdr__tenant_routing__service_schema: str = "public"


_settings = Settings()


@cache
def get_settings() -> Settings:
    """
    Entry point to access settings (ie named environment variables)
    """
    return _settings
