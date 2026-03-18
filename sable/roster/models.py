"""Pydantic models for the sable roster."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
import yaml
from pydantic import BaseModel, Field, field_validator


class Platform(BaseModel):
    handle: str  # e.g. "@tig_intern"
    platform: str = "twitter"
    url: Optional[str] = None


class Persona(BaseModel):
    archetype: str = ""         # e.g. "degen analyst", "shitposter"
    voice: str = ""             # brief description of voice/tone
    topics: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class ContentSettings(BaseModel):
    clip_style: str = "standard"        # standard | aggressive | chill
    meme_style: str = "classic"         # classic | modern | minimal
    caption_style: str = "word"         # word | phrase | none
    brainrot_energy: str = "medium"     # low | medium | high
    hashtags: list[str] = Field(default_factory=list)
    watermark: Optional[str] = None


class Account(BaseModel):
    handle: str                          # primary handle e.g. "@tig_intern"
    display_name: str = ""
    org: str = ""                        # which Sable client org this belongs to
    platforms: list[Platform] = Field(default_factory=list)
    persona: Persona = Field(default_factory=Persona)
    content: ContentSettings = Field(default_factory=ContentSettings)
    tweet_bank: list[str] = Field(default_factory=list)
    learned_preferences: dict = Field(default_factory=dict)  # written by pulse feedback
    active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, v: str) -> str:
        return v if v.startswith("@") else f"@{v}"

    def to_yaml_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_yaml_dict(cls, data: dict) -> "Account":
        return cls(**data)


class Roster(BaseModel):
    version: int = 1
    accounts: list[Account] = Field(default_factory=list)

    def get(self, handle: str) -> Optional[Account]:
        handle = handle if handle.startswith("@") else f"@{handle}"
        for acc in self.accounts:
            if acc.handle.lower() == handle.lower():
                return acc
        return None

    def upsert(self, account: Account) -> None:
        for i, acc in enumerate(self.accounts):
            if acc.handle.lower() == account.handle.lower():
                self.accounts[i] = account
                return
        self.accounts.append(account)

    def remove(self, handle: str) -> bool:
        handle = handle if handle.startswith("@") else f"@{handle}"
        before = len(self.accounts)
        self.accounts = [a for a in self.accounts if a.handle.lower() != handle.lower()]
        return len(self.accounts) < before
