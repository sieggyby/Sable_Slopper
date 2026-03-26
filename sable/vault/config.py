"""VaultConfig dataclass for sable vault settings."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VaultConfig:
    vault_base_path: str = ""       # resolved via paths.vault_dir()
    claude_model: str = ""          # falls back to cfg.get("default_model")
    auto_enrich: bool = True
    enrich_batch_size: int = 10
    min_relevance_score: int = 40
    max_suggestions: int = 5
    draft_temperature: float = 0.7
    include_media_in_export: bool = False


def load_vault_config() -> VaultConfig:
    """Load vault config from sable config, with defaults."""
    from sable import config as cfg
    return VaultConfig(
        vault_base_path=cfg.get("vault_base_path", ""),
        claude_model=cfg.get("vault_claude_model", "") or cfg.get("default_model", ""),
        auto_enrich=cfg.get("vault_auto_enrich", True),
        enrich_batch_size=int(cfg.get("vault_enrich_batch_size", 10)),
        min_relevance_score=int(cfg.get("vault_min_relevance_score", 40)),
        max_suggestions=int(cfg.get("vault_max_suggestions", 5)),
        draft_temperature=float(cfg.get("vault_draft_temperature", 0.7)),
        include_media_in_export=cfg.get("vault_include_media_in_export", False),
    )
