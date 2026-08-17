from python_backend.algorithms.contracts import AlgorithmDescriptor

PARAMETER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "prompt": {
            "type": "string",
            "default": "",
            "maxLength": 520,
        },
        "confidence_threshold": {
            "type": "number",
            "minimum": 0.05,
            "maximum": 0.95,
            "default": 0.35,
        },
        "max_instances": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "default": 5,
        },
        "mask_iou_threshold": {
            "type": "number",
            "minimum": 0.3,
            "maximum": 0.95,
            "default": 0.7,
        },
        "foreground_coverage_threshold": {
            "type": "number",
            "minimum": 0.05,
            "maximum": 0.8,
            "default": 0.2,
        },
        "edge_strength": {
            "type": "number",
            "minimum": 0,
            "maximum": 1.5,
            "default": 0.65,
        },
        "outline_strength": {
            "type": "number",
            "minimum": 0,
            "maximum": 0.3,
            "default": 0.1,
        },
    },
}


def build_descriptor(
    *,
    available: bool,
    unavailable_reason: str | None = None,
) -> AlgorithmDescriptor:
    return AlgorithmDescriptor(
        algorithm_id="tiny_model",
        version="1.0.0",
        parameter_schema=PARAMETER_SCHEMA,
        is_default=False,
        requires_gpu=True,
        supports_batching=False,
        removes_background=True,
        available=available,
        unavailable_reason=unavailable_reason,
    )
