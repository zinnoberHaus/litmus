from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    tenant_mode: str
    default_org_slug: str
    embed_cache_seconds: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "LITMUS_DATABASE_URL",
                "sqlite:///./litmus_api.db",
            ),
            tenant_mode=os.getenv("LITMUS_TENANT_MODE", "single"),
            default_org_slug=os.getenv("LITMUS_DEFAULT_ORG", "default"),
            embed_cache_seconds=int(os.getenv("LITMUS_EMBED_CACHE_SECONDS", "600")),
        )


def get_settings() -> Settings:
    return Settings.from_env()
