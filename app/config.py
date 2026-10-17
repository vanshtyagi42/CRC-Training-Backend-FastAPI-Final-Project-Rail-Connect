from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    secret_key: str
    database_url: str = "sqlite:///./railconnect.db"
    access_token_minutes: int = 30
    reset_token_minutes: int = 15
    admin_name: str = "RailConnect Admin"
    admin_email: str
    admin_password: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()