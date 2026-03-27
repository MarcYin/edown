from __future__ import annotations

import os
from typing import Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .errors import AuthenticationError
from .logging_utils import get_logger


@retry(
    retry=retry_if_exception_type(AuthenticationError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def initialize_earth_engine(server_url: Optional[str] = None) -> str:
    import ee

    logger = get_logger("edown.auth")
    service_account = os.environ.get("GEE_SERVICE_ACCOUNT")
    private_key_path = os.environ.get("GEE_SERVICE_ACCOUNT_KEY")
    try:
        if service_account and private_key_path:
            credentials = ee.ServiceAccountCredentials(service_account, private_key_path)
            if server_url:
                ee.Initialize(credentials=credentials, opt_url=server_url)
            else:
                ee.Initialize(credentials=credentials)
            logger.debug("Initialized Earth Engine with service account credentials.")
            return "service-account"

        if server_url:
            ee.Initialize(opt_url=server_url)
        else:
            ee.Initialize()
        logger.debug("Initialized Earth Engine with default credentials.")
        return "default"
    except Exception as exc:
        raise AuthenticationError(
            "Failed to initialize Earth Engine. Set service-account credentials or "
            "configure Earth Engine user authentication."
        ) from exc
