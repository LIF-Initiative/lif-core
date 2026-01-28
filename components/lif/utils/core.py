"""Core utilities for the LIF system."""

import os
import sys
from typing import Dict, List

from lif.exceptions.core import MissingEnvironmentVariableException


def check_required_env_vars(
    required_vars: List[str], 
    raise_exception: bool = True,
    logger=None
) -> Dict[str, str]:
    """Check that all required environment variables are set.
    
    Args:
        required_vars: List of environment variable names to check
        raise_exception: If True, raise MissingEnvironmentVariableException.
                        If False, log critical error and exit with sys.exit(1)
        logger: Optional logger instance for error reporting
        
    Returns:
        Dict[str, str]: Dictionary mapping env var names to their values
        
    Raises:
        MissingEnvironmentVariableException: If raise_exception=True and vars are missing
        
    Examples:
        >>> env_vars = check_required_env_vars(["DATABASE_URL", "API_KEY"])
        >>> database_url = env_vars["DATABASE_URL"]
        
        >>> # For server applications that should exit on missing config
        >>> check_required_env_vars(["CONFIG_FILE"], raise_exception=False, logger=logger)
    """
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        error_msg = f"Missing required environment variables: {', '.join(missing)}"
        
        if raise_exception:
            # For libraries and components that should raise exceptions
            if len(missing) == 1:
                raise MissingEnvironmentVariableException(missing[0])
            else:
                # For multiple missing vars, use a generic message
                from lif.exceptions.core import LIFException
                raise LIFException(error_msg)
        else:
            # For standalone applications that should exit
            if logger:
                logger.critical(error_msg)
            else:
                print(f"CRITICAL: {error_msg}", file=sys.stderr)
            sys.exit(1)
    
    # Return the validated environment variables
    result = {}
    for var in required_vars:
        value = os.getenv(var)
        if value is not None:  # We know this is true since we checked above
            result[var] = value
    return result


def get_required_env_var(var_name: str) -> str:
    """Get a single required environment variable.
    
    Args:
        var_name: Name of the environment variable
        
    Returns:
        str: The environment variable value
        
    Raises:
        MissingEnvironmentVariableException: If the variable is not set
        
    Examples:
        >>> database_url = get_required_env_var("DATABASE_URL")
    """
    value = os.getenv(var_name)
    if not value:
        raise MissingEnvironmentVariableException(var_name)
    return value