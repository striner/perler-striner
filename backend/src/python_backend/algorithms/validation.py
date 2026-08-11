from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .contracts import AlgorithmIdentity, AlgorithmInput, AlgorithmOutput
from .errors import AlgorithmContractError, InvalidRequestError


def validate_algorithm_params(params: Mapping[str, Any], max_depth: int, max_fields: int) -> None:
    field_count = 0

    def visit(value: Any, depth: int) -> None:
        nonlocal field_count
        if depth > max_depth:
            raise InvalidRequestError("algorithm_params is too deeply nested")
        if isinstance(value, Mapping):
            field_count += len(value)
            if field_count > max_fields:
                raise InvalidRequestError("algorithm_params contains too many fields")
            for key, nested in value.items():
                normalized = str(key).replace("_", "").replace("-", "").lower()
                if normalized in {"removebackground", "backgroundremoval"}:
                    raise InvalidRequestError("background removal cannot be disabled")
                visit(nested, depth + 1)
        elif isinstance(value, list):
            for nested in value:
                visit(nested, depth + 1)
        elif isinstance(value, float) and not math.isfinite(value):
            raise InvalidRequestError("algorithm_params contains a non-finite number")
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise InvalidRequestError("algorithm_params contains an unsupported value")

    visit(params, 1)


def validate_algorithm_output(request: AlgorithmInput, output: object) -> None:
    if not isinstance(output, AlgorithmOutput):
        raise AlgorithmContractError()
    if type(output.schema_version) is not int:
        raise AlgorithmContractError()
    if not isinstance(output.algorithm, AlgorithmIdentity):
        raise AlgorithmContractError()
    if not isinstance(output.algorithm.algorithm_id, str):
        raise AlgorithmContractError()
    if not isinstance(output.algorithm.version, str) or not output.algorithm.version:
        raise AlgorithmContractError()
    if type(output.width) is not int or type(output.height) is not int:
        raise AlgorithmContractError()
    expected_version = request.algorithm.version
    if output.schema_version != request.schema_version:
        raise AlgorithmContractError()
    if output.algorithm.algorithm_id != request.algorithm.algorithm_id:
        raise AlgorithmContractError()
    if expected_version is not None and output.algorithm.version != expected_version:
        raise AlgorithmContractError()
    if output.width != request.target.width or output.height != request.target.height:
        raise AlgorithmContractError()
    if not isinstance(output.rgba, bytes):
        raise AlgorithmContractError()
    if len(output.rgba) != output.width * output.height * 4:
        raise AlgorithmContractError()
