"""Team Channel - Comunicación entre entidades."""
import json
from pathlib import Path
from datetime import datetime


class TeamChannel:
    def __init__(self, own_path: Path, other_path: Path):
        self.own_storage = own_path / "team_inbox.json"
        self.other_storage = other_path / "team_inbox.json"
        self.own_storage.parent.mkdir(parents=True, exist_ok=True)
        self.other_storage.parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self, path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except:
                return {}
        return {}
    
    def _save(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    
    def send(self, sender: str, receiver: str, message: str, msg_type: str = "message"):
        """Envía mensaje a la bandeja del receptor."""
        target_path = self.other_storage if receiver != sender else self.own_storage
        inbox = self._load(target_path)
        if receiver not in inbox:
            inbox[receiver] = []
        inbox[receiver].append({
            "sender": sender,
            "type": msg_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "read": False
        })
        self._save(target_path, inbox)
    
    def check(self, receiver: str) -> list:
        """Revisa mensajes pendientes en su propia bandeja."""
        inbox = self._load(self.own_storage)
        messages = [m for m in inbox.get(receiver, []) if not m.get("read")]
        for m in messages:
            m["read"] = True
        self._save(self.own_storage, inbox)
        return messages
    
    def clear(self, receiver: str):
        """Limpia la bandeja del receptor."""
        inbox = self._load(self.own_storage)
        if receiver in inbox:
            inbox[receiver] = []
            self._save(self.own_storage, inbox)


def setup(flow_manager):
    from config import ENTITY_DATA_DIR
    from pathlib import Path
    import json
    
    own_dir = ENTITY_DATA_DIR / "memory"
    
    mod_json = Path(__file__).parent / "mod.json"
    secondary_path = None
    if mod_json.exists():
        metadata = json.loads(mod_json.read_text(encoding="utf-8"))
        secondary_path = metadata.get("config", {}).get("secondary_entity_path")
    
    if secondary_path:
        other_dir = Path(secondary_path) / "memory"
    else:
        other_dir = own_dir
    
    channel = TeamChannel(own_dir, other_dir)
    flow_manager._team_channel = channel
    print(f"   [TeamChannel] Ready. Secondary: {other_dir}")
    return channel


def teardown(flow_manager):
    flow_manager._team_channel = None