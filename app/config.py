from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_service_role_key: str

    telegram_user_bot_token: str
    telegram_admin_bot_token: str
    webhook_base_url: str

    user_webhook_secret: str
    admin_webhook_secret: str

    telegram_admin_id: int = 8242998457
    telegram_admin_group_id: int = -1004434268756

    topic_users: int = 4
    topic_deposits: int = 7
    topic_withdrawals: int = 8
    topic_ai_bot: int = 9
    topic_trading: int = 10
    topic_referrals: int = 11
    topic_errors: int = 12
    topic_reports: int = 13
    topic_system: int = 14
    topic_finance: int = 16

    deposit_asset: str = "USDT"
    deposit_network: str = "TRC20"
    deposit_address: str
    min_deposit: float = 10
    min_withdrawal: float = 50

    @property
    def topic_map(self) -> dict[str, int]:
        return {
            "users": self.topic_users,
            "deposits": self.topic_deposits,
            "withdrawals": self.topic_withdrawals,
            "ai_bot": self.topic_ai_bot,
            "trading": self.topic_trading,
            "referrals": self.topic_referrals,
            "errors": self.topic_errors,
            "reports": self.topic_reports,
            "system": self.topic_system,
            "finance": self.topic_finance,
        }


settings = Settings()
