from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./harmony.db"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

