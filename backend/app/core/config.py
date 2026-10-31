from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., alias="DATABASE_URL")
    
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    
    # API Security
    api_secret_key: str = Field(..., alias="API_SECRET_KEY")
    
    # Alpaca
    alpaca_api_key: str = Field(..., alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(..., alias="ALPACA_SECRET_KEY")
    alpaca_paper: bool = Field(default=True, alias="ALPACA_PAPER")
    
    # MLflow
    mlflow_tracking_uri: str = Field(default="file:./mlruns", alias="MLFLOW_TRACKING_URI")
    
    # SEC
    sec_user_agent: str = Field(default="StockAgent/1.0 (admin@yourdomain.com)", alias="SEC_USER_AGENT")
    
    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")
    
    # Scheduler
    enable_scheduler: bool = Field(default=True, alias="ENABLE_SCHEDULER")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()