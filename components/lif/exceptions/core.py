class LIFException(Exception):
    """Base exception for LIF."""

    pass


class DataStoreException(LIFException):
    """Raised when there is an issue with the data store."""

    def __init__(self, message="Data store error occurred"):
        super().__init__(message)


class DataNotFoundException(DataStoreException):
    """Raised when data is not found in the data store."""

    def __init__(self, message="Data not found"):
        super().__init__(message)


class InvalidInputException(LIFException):
    """Raised when input data is invalid."""

    def __init__(self, message="Invalid input provided"):
        super().__init__(message)


class MissingEnvironmentVariableException(LIFException):
    """Raised when a required environment variable is missing."""

    def __init__(self, var_name):
        self.var_name = var_name
        super().__init__(f"Required environment variable '{var_name}' is not set.")


class OrchestratorStatusMappingError(RuntimeError):
    """Raised when an external orchestrator status cannot be mapped to an internal OrchestratorJobStatus."""

    def __init__(self, orchestrator_name: str, raw_status: str):
        super().__init__(f"Unmapped status '{raw_status}' from orchestrator '{orchestrator_name}'")
        self.orchestrator_name = orchestrator_name
        self.raw_status = raw_status


class ResourceNotFoundException(LIFException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_id, message=None):
        self.resource_id = resource_id
        super().__init__(message if message else f"Resource with ID '{resource_id}' not found.")
