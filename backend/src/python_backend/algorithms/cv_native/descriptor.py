from python_backend.algorithms.contracts import AlgorithmDescriptor

DESCRIPTOR = AlgorithmDescriptor(
    algorithm_id="cv_native",
    version="1.0.0",
    is_default=True,
    requires_gpu=False,
    supports_batching=False,
    removes_background=True,
    parameter_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
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
            "background_recovery_distance": {
                "type": "number",
                "minimum": 0,
                "maximum": 40,
                "default": 6,
            },
            "coarse_subject_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "default": 1,
            },
            "protection_scale": {
                "type": "number",
                "minimum": 1,
                "maximum": 4,
                "default": 2,
            },
            "foreground_seed_distance": {
                "type": "number",
                "minimum": 0,
                "maximum": 80,
                "default": 28,
            },
            "edge_seed_threshold": {
                "type": "number",
                "minimum": 0,
                "maximum": 255,
                "default": 56,
            },
            "saturation_seed_threshold": {
                "type": "number",
                "minimum": 0,
                "maximum": 255,
                "default": 18,
            },
            "protection_dilation_radius": {
                "type": "integer",
                "minimum": 0,
                "maximum": 12,
                "default": 2,
            },
            "recovery_neighborhood_ratio": {
                "type": "number",
                "minimum": 0.002,
                "maximum": 0.05,
                "default": 0.014,
            },
            "foreground_coverage_threshold": {
                "type": "number",
                "minimum": 0.05,
                "maximum": 0.8,
                "default": 0.2,
            },
        },
    },
)
