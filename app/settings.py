from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def api_key() -> str:
    for name in ('YUANBAO_API_KEY', 'yuanbao_search'):
        if os.getenv(name, '').strip():
            return os.environ[name].strip()
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as handle:
                return str(winreg.QueryValueEx(handle, 'yuanbao_search')[0]).strip()
        except OSError:
            pass
    return ''


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    key: str
    trust_env: bool = True
    access_token: str = ''

    @classmethod
    def load(cls) -> 'Settings':
        return cls(
            data_dir=Path(os.getenv('DATA_DIR', str(ROOT / 'data'))),
            key=api_key(),
            trust_env=os.getenv('USE_ENV_PROXY', 'true').lower() == 'true',
            access_token=os.getenv('APP_ACCESS_TOKEN', ''),
        )
