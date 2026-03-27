from __future__ import annotations

import importlib
from typing import Any, Callable, Optional, cast

from .errors import ConfigurationError

TransformPlugin = Callable[[Any, dict[str, Any], Any], Any]


def load_transform_plugin(spec: Optional[str]) -> Optional[TransformPlugin]:
    if spec is None:
        return None
    if ":" not in spec:
        raise ConfigurationError("transform plugin must use the format 'module:function'.")
    module_name, attribute_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    plugin = getattr(module, attribute_name, None)
    if plugin is None or not callable(plugin):
        raise ConfigurationError(f"Transform plugin '{spec}' is not callable.")
    return cast(TransformPlugin, plugin)
