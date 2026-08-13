from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PYTHON_BACKEND_",
        extra="ignore",
    )

    app_name: str = "python-backend"
    cors_origins: str = "http://localhost:4321,http://127.0.0.1:4321"
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    max_grid_size: int = Field(default=150, ge=1, le=4096)
    max_algorithm_params_bytes: int = Field(default=16 * 1024, ge=2)
    max_algorithm_params_depth: int = Field(default=8, ge=1, le=32)
    max_algorithm_params_fields: int = Field(default=128, ge=1)
    request_timeout_seconds: float = Field(default=30, gt=0)
    queue_timeout_seconds: float = Field(default=5, gt=0)
    max_inflight_requests: int = Field(default=128, ge=1)
    max_decoded_pixels: int = Field(default=40_000_000, ge=1)
    cv_work_max_edge: int = Field(default=1024, ge=128, le=4096)
    cv_max_concurrency: int = Field(default=2, ge=1, le=64)
    cv_opencv_threads: int = Field(default=1, ge=1, le=64)
    bento_workers: int = Field(default=1, ge=1)
    bento_replicas: int = Field(default=1, ge=1)
    bento_max_concurrency: int = Field(default=32, ge=1)
    gpu_resource_count: float = Field(default=1, ge=0)
    max_batch_size: int = Field(default=8, ge=1)
    max_batch_latency_ms: int = Field(default=25, ge=1)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
