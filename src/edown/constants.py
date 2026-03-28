DEFAULT_HIGH_VOLUME_URL = "https://earthengine-highvolume.googleapis.com"
DEFAULT_COLLECTION_CHUNK_LIMIT = 5000
DEFAULT_BLOCK_SIZE = 256
DEFAULT_PREPARE_WORKERS = 10
DEFAULT_DOWNLOAD_WORKERS = 10
DEFAULT_MAX_INFLIGHT_CHUNKS = 32
DEFAULT_MAX_RETRIES = 4
DEFAULT_RETRY_DELAY_SECONDS = 2.0
DEFAULT_REQUEST_BYTE_LIMIT = 48 * 1024 * 1024
MANIFEST_SCHEMA_VERSION = 1

PRECISION_TO_DTYPE = {
    "int": "int16",
    "float": "float32",
    "double": "float64",
    "uint8": "uint8",
    "uint16": "uint16",
    "uint32": "uint32",
    "int8": "int8",
    "int16": "int16",
    "int32": "int32",
    "int64": "int64",
    "float32": "float32",
    "float64": "float64",
}
