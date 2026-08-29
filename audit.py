"""Local JSON audit trail helpers."""

import json
from pathlib import Path
from threading import Lock

from models import AuditEntry

AUDIT_LOG_PATH = Path(__file__).with_name("audit_log.json")
_AUDIT_LOCK = Lock()


def load_audit_entries(path: Path | None = None) -> list[dict[str, object]]:
    """Load and validate all entries from the local audit trail."""

    target = path or AUDIT_LOG_PATH
    if not target.exists():
        return []

    content = target.read_text(encoding="utf-8").strip()
    if not content:
        return []

    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError("audit_log.json must contain a JSON array")

    return [
        AuditEntry.model_validate(entry).model_dump(mode="json")
        for entry in data
    ]


def append_audit_entry(
    entry: AuditEntry,
    path: Path | None = None,
) -> dict[str, object]:
    """Append one entry without discarding the existing audit history."""

    target = path or AUDIT_LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    with _AUDIT_LOCK:
        entries = load_audit_entries(target)
        serialized_entry = entry.model_dump(mode="json")
        entries.append(serialized_entry)

        temporary_path = target.with_suffix(f"{target.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(target)

    return serialized_entry


__all__ = ["AUDIT_LOG_PATH", "append_audit_entry", "load_audit_entries"]
