from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = ""
    mongodb_host: str = ""
    mongodb_user: str = ""
    mongodb_password: str = ""
    mongodb_db: str = "agentshield"

    llm_api_key: str = ""
    llm_model_reasoning: str = "gpt-5.6-luna"
    llm_model_fast: str = "gpt-5.6-luna"
    llm_record: bool = False
    llm_replay: bool = False

    voyage_api_key: str = ""
    voyage_base_url: str = "https://api.voyageai.com/v1"
    voyage_model: str = "voyage-4-large"
    embedding_dim: int = 1024

    fp_threshold: float = 0.01
    approver: str = "akhil"
    gateway_url: str = "http://127.0.0.1:8765"

    def resolved_mongodb_uri(self) -> str:
        if self.mongodb_uri:
            return self.mongodb_uri
        if not (self.mongodb_host and self.mongodb_user and self.mongodb_password):
            raise ValueError(
                "Set MONGODB_URI, or MONGODB_HOST + MONGODB_USER + MONGODB_PASSWORD in .env"
            )
        user = quote_plus(self.mongodb_user)
        password = quote_plus(self.mongodb_password)
        return (
            f"mongodb+srv://{user}:{password}@{self.mongodb_host}/"
            "?retryWrites=true&w=majority&appName=agentshield"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
