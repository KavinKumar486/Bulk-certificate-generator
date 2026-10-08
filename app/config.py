import os
from pathlib import Path


class Settings:
    def __init__(self):
        self.API_KEY: str = os.getenv("API_KEY", "dev-secret-key")
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
        self.STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", "./storage"))
        self.MAX_RECIPIENTS_PER_REQUEST: int = int(os.getenv("MAX_RECIPIENTS_PER_REQUEST", "1000"))


settings = Settings()
