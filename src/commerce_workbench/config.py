from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8787

    def __post_init__(self) -> None:
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Only a loopback host is supported")
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        object.__setattr__(self, "data_dir", Path(self.data_dir).expanduser().resolve())

    @property
    def database_path(self) -> Path:
        return self.data_dir / "workbench.sqlite3"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            data_dir=Path(os.environ.get("CW_DATA_DIR", "data")),
            host=os.environ.get("CW_HOST", "127.0.0.1"),
            port=int(os.environ.get("CW_PORT", "8787")),
        )
