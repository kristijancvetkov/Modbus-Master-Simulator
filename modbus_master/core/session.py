import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


APP_DIR = Path.home() / ".modbus_master_simulator"
LAST_SESSION_FILE = APP_DIR / "last_session.json"


@dataclass
class SessionData:
    connection: Dict[str, Any] = field(default_factory=dict)
    registers: List[Dict[str, Any]] = field(default_factory=list)
    poll_interval_ms: int = 1000
    scanner: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection": self.connection,
            "registers": self.registers,
            "poll_interval_ms": self.poll_interval_ms,
            "scanner": self.scanner,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        return cls(
            connection=data.get("connection", {}),
            registers=data.get("registers", []),
            poll_interval_ms=int(data.get("poll_interval_ms", 1000)),
            scanner=data.get("scanner", {}),
        )


def save_session(path: Path, session: SessionData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")


def load_session(path: Path) -> SessionData:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionData.from_dict(data)


def save_last_session(session: SessionData) -> None:
    save_session(LAST_SESSION_FILE, session)


def load_last_session() -> SessionData:
    if LAST_SESSION_FILE.exists():
        return load_session(LAST_SESSION_FILE)
    return SessionData()
