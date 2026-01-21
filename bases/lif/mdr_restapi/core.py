from http import HTTPStatus
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from lif.mdr_auth.core import AuthMiddleware, create_access_token, create_refresh_token, decode_jwt
from lif.mdr_restapi import (
    attribute_endpoints,
    datamodel_constraints_endpoints,
    datamodel_endpoints,
    entity_association_endpoints,
    entity_attribute_association_endpoints,
    entity_endpoints,
    generate_jinja_endpoint,
    import_export_endpoints,
    inclusions_endpoints,
    search_endpoint,
    transformation_endpoint,
    value_mapping_endpoints,
    value_set_values_endpoint,
    valueset_endpoint,
)
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.logger_config import get_logger
from passlib.context import CryptContext
from pydantic import BaseModel

logger = get_logger(__name__)

app = FastAPI(title="LIF Metadata Repository API", description="API for the LIF Metadata Repository", version="1.0.0")

settings = get_settings()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Mock Database and State ---
users_db: List[Dict[str, Any]] = [
    {
        "username": "atsatrian_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Alan",
        "lastname": "Tsatrian",  # cspell:disable-line
        "identifier": "100001",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "jdiaz_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Jenna",
        "lastname": "Diaz",  # cspell:disable-line
        "identifier": "100002",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "smarin_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Sarah",
        "lastname": "Marin",
        "identifier": "100003",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "Rgreen11Fdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Renee",
        "lastname": "Green",
        "identifier": "100004",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "mhanson_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Matt",
        "lastname": "Hanson",
        "identifier": "100005",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "tthatcher_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Tracy",
        "lastname": "Thatcher",
        "identifier": "100006",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "nsmith_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Nancy",
        "lastname": "Smith",
        "identifier": "100007",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "bwang_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Ben",
        "lastname": "Wang",
        "identifier": "100008",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "gdavis_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "George",
        "lastname": "Davis",
        "identifier": "100009",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "cwilliams_lifdemo@stateu.edu",
        "password": "$2b$12$pJyJLoYE2QcygmcdEfUhx.7OW1hbo79e3CbrHTyKy7ATJyUPRB4CK",  # "liffy4life!"
        "firstname": "Caleb",
        "lastname": "Williams",
        "identifier": "100010",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
]


# Store active refresh tokens: username -> token
refresh_tokens_store: Dict[str, str] = {}


# --- Pydantic Models ---
class LoginRequest(BaseModel):
    username: str
    password: str


class UserDetails(BaseModel):
    username: str
    firstname: str
    lastname: str
    identifier: str
    identifier_type: str
    identifier_type_enum: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: UserDetails
    access_token: str
    refresh_token: str


class LogoutResponse(BaseModel):
    success: bool


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str


class HealthCheck(BaseModel):
    status: HTTPStatus
    message: str


app.add_middleware(AuthMiddleware)

# Configure CORS middleware
cors_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
cors_methods = [method.strip() for method in settings.cors_allow_methods.split(",") if method.strip()]
cors_headers = (
    [header.strip() for header in settings.cors_allow_headers.split(",") if header.strip()]
    if settings.cors_allow_headers != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)


# Add pagination to the FastAPI app
# add_pagination(app)


# --- Authentication Helper Functions ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return pwd_context.hash(password)


def find_user(username: str, password: str) -> Dict[str, Any] | None:
    """Find user by username and verify password"""
    logger.info(f"Looking for user: {username}")
    for user in users_db:
        if user["username"] == username:
            logger.info(f"Found user {username}, verifying password...")
            if verify_password(password, user["password"]):
                logger.info(f"Password verification successful for {username}")
                return user
            else:
                logger.warning(f"Password verification failed for {username}")
                return None
    logger.warning(f"User not found: {username}")
    return None


# --- API Endpoints ---


@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Login endpoint"""
    logger.info(f"Login attempt for username: {request.username}")

    user = find_user(request.username, request.password)
    if not user:
        logger.warning(f"Login failed for username: {request.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    logger.info(f"Login successful for username: {request.username}")

    # Create tokens
    access_token = create_access_token(data={"sub": user["username"]})
    refresh_token = create_refresh_token(data={"sub": user["username"]})

    # Store refresh token
    refresh_tokens_store[user["username"]] = refresh_token

    # Create user details response
    user_details = UserDetails(
        username=user["username"],
        firstname=user["firstname"],
        lastname=user["lastname"],
        identifier=user["identifier"],
        identifier_type=user["identifier_type"],
        identifier_type_enum=user["identifier_type_enum"],
    )

    return LoginResponse(
        success=True,
        message="Login successful",
        user=user_details,
        access_token=access_token,
        refresh_token=refresh_token,
    )


@app.post("/refresh-token", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest) -> RefreshTokenResponse:
    """Refresh access token using refresh token"""
    try:
        payload = decode_jwt(request.refresh_token)

        # Validate token type
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        username = payload.get("sub")
        if not username or refresh_tokens_store.get(username) != request.refresh_token:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Create new access token
        access_token = create_access_token(data={"sub": username})

        return RefreshTokenResponse(access_token=access_token)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@app.post("/logout", response_model=LogoutResponse)
async def logout(request: Request) -> LogoutResponse:
    """Logout endpoint"""
    username = request.state.principal
    # Remove refresh token
    if username in refresh_tokens_store:
        del refresh_tokens_store[username]

    return LogoutResponse(success=True)


@app.get("/health-check", response_model=HealthCheck)
async def health_check():
    """
    Health check endpoint to verify the API is running
    """
    return HealthCheck(status=HTTPStatus.OK, message="API is healthy")


app.include_router(datamodel_endpoints.router, prefix="/datamodels")

app.include_router(entity_endpoints.router, prefix="/entities")

app.include_router(entity_association_endpoints.router, prefix="/entity_associations")

app.include_router(attribute_endpoints.router, prefix="/attributes")

app.include_router(entity_attribute_association_endpoints.router, prefix="/entity_attribute_associations")

app.include_router(inclusions_endpoints.router, prefix="/inclusions")

app.include_router(valueset_endpoint.router, prefix="/value_sets")

app.include_router(value_set_values_endpoint.router, prefix="/value_set_values")

app.include_router(transformation_endpoint.router, prefix="/transformation_groups")

app.include_router(search_endpoint.router, prefix="/search")

app.include_router(value_mapping_endpoints.router, prefix="/value_mappings")


app.include_router(import_export_endpoints.router, prefix="/import_export")

app.include_router(generate_jinja_endpoint.router, prefix="/generate_jinja")


app.include_router(datamodel_constraints_endpoints.router, prefix="/datamodel_constraints")


# API Key Management Endpoints
class APIKeyRequest(BaseModel):
    service_name: str


class APIKeyResponse(BaseModel):
    api_key: str
    service_name: str
    message: str


class APIKeysListResponse(BaseModel):
    api_keys: Dict[str, str]


# Test endpoint demonstrating dual authentication
@app.get("/test/auth-info")
async def get_auth_info(request: Request) -> Dict[str, Any]:
    """Test endpoint that accepts both JWT tokens and API keys"""
    if request.state.principal.startswith("service:"):
        return {
            "authenticated_as": "microservice",
            "service_name": request.state.principal.replace("service:", ""),
            "auth_type": "API key",
        }
    return {"authenticated_as": "user", "username": request.state.principal, "auth_type": "JWT token"}
