"""
skodaconnect - A Python 3 library for interacting with Skoda Connect and Smartlink services.

For more details and documentation, visit the github page at https://github.com/lendy007/skodaconnect
"""

import skodaconnect.const as const
from skodaconnect.connection import Connection
from skodaconnect.exceptions import (
    SkodaConfigException,
    SkodaAuthenticationException,
    SkodaAccountLockedException,
    SkodaTokenExpiredException,
    SkodaException,
    SkodaEULAException,
    SkodaThrottledException,
    SkodaLoginFailedException,
    SkodaInvalidRequestException,
    SkodaRequestInProgressException
)

from .__version__ import __version__

__all__ = [
    "Controller",
    "SubaruException",
    "InvalidCredentials",
    "InvalidPIN",
    "IncompleteCredentials",
    "PINLockoutProtect",
    "RemoteServiceFailure",
    "VehicleNotSupported",
    "const",
    "__version__",
]

__pdoc__ = {"app": False}