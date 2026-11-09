"""Local env loading without shell interpolation. Never print secret values."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def load():
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if line and not line.startswith('#'):
                key,value=line.split('=',1)
                os.environ.setdefault(key,value)
    return os.environ
