class EdownError(Exception):
    """Base error for the package."""


class ConfigurationError(EdownError):
    """Raised when configuration is invalid."""


class AuthenticationError(EdownError):
    """Raised when Earth Engine authentication fails."""


class DiscoveryError(EdownError):
    """Raised when collection discovery fails."""


class DownloadError(EdownError):
    """Raised when downloading raster chunks fails."""


class StackError(EdownError):
    """Raised when Zarr stack creation fails."""
