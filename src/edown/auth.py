from __future__ import annotations

import os
from typing import Any, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .errors import AuthenticationError
from .logging_utils import get_logger

EE_SCOPE = "https://www.googleapis.com/auth/earthengine"


def _initialize_default_credentials(ee_module: Any, server_url: Optional[str]) -> None:
    if server_url:
        ee_module.Initialize(opt_url=server_url)
    else:
        ee_module.Initialize()


def _initialize_service_account(
    ee_module: Any, service_account: str, private_key_path: str, server_url: Optional[str]
) -> None:
    credentials = ee_module.ServiceAccountCredentials(service_account, private_key_path)
    if server_url:
        ee_module.Initialize(credentials=credentials, opt_url=server_url)
    else:
        ee_module.Initialize(credentials=credentials)


def _candidate_projects(default_project: Optional[str], credentials: Any) -> list[Optional[str]]:
    values = [
        default_project,
        os.environ.get("GOOGLE_CLOUD_PROJECT"),
        os.environ.get("GCLOUD_PROJECT"),
        getattr(credentials, "quota_project_id", None),
    ]
    ordered: list[Optional[str]] = []
    seen: set[Optional[str]] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _initialize_adc_credentials(ee_module: Any, server_url: Optional[str]) -> None:
    import google.auth

    credentials, default_project = google.auth.default(scopes=[EE_SCOPE])
    errors: list[str] = []
    for project in _candidate_projects(default_project, credentials):
        try:
            init_kwargs: dict[str, Any] = {"credentials": credentials}
            if server_url:
                init_kwargs["opt_url"] = server_url
            if project:
                init_kwargs["project"] = project
            ee_module.Initialize(**init_kwargs)
            return
        except Exception as exc:
            project_label = project or "<none>"
            errors.append(f"project={project_label}: {exc}")
    raise AuthenticationError("ADC initialization failed. " + " | ".join(errors))


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
    failures: list[str] = []

    if service_account and private_key_path:
        try:
            _initialize_service_account(ee, service_account, private_key_path, server_url)
            logger.debug("Initialized Earth Engine with service account credentials.")
            return "service-account"
        except Exception as exc:
            failures.append(f"service-account: {exc}")

    try:
        _initialize_default_credentials(ee, server_url)
        logger.debug("Initialized Earth Engine with persistent Earth Engine credentials.")
        return "default"
    except Exception as exc:
        failures.append(f"default: {exc}")

    try:
        _initialize_adc_credentials(ee, server_url)
        logger.debug("Initialized Earth Engine with application default credentials.")
        return "adc"
    except Exception as exc:
        failures.append(f"adc: {exc}")

    raise AuthenticationError(
        "Failed to initialize Earth Engine. Reauthenticate with Earth Engine or provide "
        f"service-account credentials. Attempts: {'; '.join(failures)}"
    )
