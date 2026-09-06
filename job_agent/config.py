\
from __future__ import annotations

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]

def load_settings(path: str | None = None) -> dict:
    settings_path = Path(path) if path else BASE_DIR / "config" / "settings.yaml"
    with settings_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)
