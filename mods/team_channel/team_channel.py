"""Canal de comunicación entre entidades Sibelium."""
import json
from pathlib import Path
from datetime import datetime


class TeamChannel:
    def __init__(self, storage_path: Path):
        self.storage = storage_path / "team_inbox.json"
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.inbox = self._load()
    
    def _load(self) -> dict:
        if self.storage.exists():
            return json.loads(self.storage.read_text(encoding="utf-8"))
        return {}
    
    def _save(self):
        self.storage.write_text(json.dumps(self.inbox, ensure_ascii=False, indent=2))
    
    def send(self, sender: str, receiver: str, message: str, msg_type: str = "proposal"):
        if receiver not in self.inbox:
            self.inbox[receiver] = []
        self.inbox[receiver].append({
            "sender": sender,
            "type": msg_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "read": False
        })
        self._save()
    
    def check(self, receiver: str) -> list:
        messages = [m for m in self.inbox.get(receiver, []) if not m.get("read")]
        for m in messages:
            m["read"] = True
        self._save()
        return messages
    
    def clear(self, receiver: str):
        self.inbox[receiver] = []
        self._save()