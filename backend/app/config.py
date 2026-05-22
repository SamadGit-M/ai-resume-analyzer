from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    GEMINI_API_KEY: str = ""
    GEMINI_LLM_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"

    DATABASE_URL: str = "sqlite:///./data/app.db"
    CHROMA_DIR: str = "./data/chroma"
    UPLOAD_DIR: str = "./data/uploads"

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    JWT_SECRET: str = "change-me"
    JWT_EXPIRES_MINUTES: int = 720

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
