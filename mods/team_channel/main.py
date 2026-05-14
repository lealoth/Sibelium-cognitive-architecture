"""Team Channel - Comunicación entre entidades."""
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
            try:
                return json.loads(self.storage.read_text(encoding="utf-8"))
            except:
                return {}
        return {}
    
    def _save(self):
        self.storage.write_text(json.dumps(self.inbox, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def send(self, sender: str, receiver: str, message: str, msg_type: str = "message"):
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
        if receiver in self.inbox:
            self.inbox[receiver] = []
            self._save()


def setup(flow_manager):
    from config import ENTITY_DATA_DIR
    channel = TeamChannel(ENTITY_DATA_DIR / "memory")
    flow_manager._team_channel = channel
    print("   [TeamChannel] Ready.")
    return channel


def teardown(flow_manager):
    flow_manager._team_channel = None