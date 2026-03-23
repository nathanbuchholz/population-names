"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://pipeline:pipeline@localhost:5432/population_names"
    database_url_sync: str = "postgresql://pipeline:pipeline@localhost:5432/population_names"
    airflow_base_url: str = "http://airflow-webserver:8080"
    airflow_username: str = "admin"
    airflow_password: str = "airflow"
    api_key: str = "dev"
    cors_origins: str = "http://localhost:8088,http://superset:8088"
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
