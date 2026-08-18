from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: str = "production"
    demo_reset_enabled: bool = False
    database_url: str = "sqlite:///./harmony.db"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: float = 25.0
    ollama_health_timeout_seconds: float = 1.0
    ollama_unavailable_cache_seconds: float = 10.0
    ollama_failure_cache_seconds: float = 30.0
    ollama_max_output_tokens: int = 64
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def demo_reset_available(self) -> bool:
        return (self.demo_reset_enabled
                and self.app_environment.lower() in {"demo", "development", "test"})


settings = Settings()
