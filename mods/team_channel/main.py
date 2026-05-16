"""Team Channel - Comunicación entre entidades con prioridades y eventos."""
import json
from datetime import datetime
from pathlib import Path


class TeamChannel:
    """Canal de comunicación peer-to-peer con prioridades y suscripción por eventos."""

    def __init__(self, own_path: Path, other_path: Path):
        self.own_storage = own_path / "team_inbox.json"
        self.other_storage = other_path / "team_inbox.json"
        self.own_storage.parent.mkdir(parents=True, exist_ok=True)
        self.other_storage.parent.mkdir(parents=True, exist_ok=True)
        # Suscripciones a eventos
        self._subscribers = {}

    # ============================================
    # API PÚBLICA
    # ============================================

    def send(self, sender: str, receiver: str, message: str,
             msg_type: str = "message", priority: float = 0.5,
             event: str = None):
        """Envía mensaje con prioridad y evento opcional."""
        target_path = self.other_storage if receiver != sender else self.own_storage
        inbox = self._load(target_path)
        if receiver not in inbox:
            inbox[receiver] = []
        inbox[receiver].append({
            "sender": sender,
            "type": msg_type,
            "message": message,
            "priority": max(0.0, min(1.0, priority)),
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "read": False
        })
        self._save(target_path, inbox)

    def check(self, receiver: str) -> list:
        """Revisa mensajes pendientes ordenados por prioridad."""
        inbox = self._load(self.own_storage)
        messages = [m for m in inbox.get(receiver, []) if not m.get("read")]
        for m in messages:
            m["read"] = True
        self._save(self.own_storage, inbox)
        # Ordenar por prioridad (mayor primero)
        messages.sort(key=lambda m: m.get("priority", 0.5), reverse=True)
        return messages

    def check_by_event(self, receiver: str, event: str) -> list:
        """Revisa mensajes de un evento específico."""
        inbox = self._load(self.own_storage)
        messages = [
            m for m in inbox.get(receiver, [])
            if not m.get("read") and m.get("event") == event
        ]
        for m in messages:
            m["read"] = True
        self._save(self.own_storage, inbox)
        return messages

    def subscribe(self, event: str, callback):
        """Suscribe un callback a un evento."""
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(callback)

    def publish(self, sender: str, event: str, message: str, priority: float = 0.5):
        """Publica un evento a todos los suscriptores locales."""
        if event in self._subscribers:
            for callback in self._subscribers[event]:
                try:
                    callback(sender, message, priority)
                except Exception as e:
                    print(f"   [TeamChannel] Error en callback de {event}: {e}")

    def clear(self, receiver: str):
        inbox = self._load(self.own_storage)
        if receiver in inbox:
            inbox[receiver] = []
            self._save(self.own_storage, inbox)

    # ============================================
    # PERSISTENCIA
    # ============================================

    def _load(self, path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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

    # Suscribir a eventos internos
    channel.subscribe("code_review", _on_code_review)
    channel.subscribe("director_feedback", _on_director_feedback)

    print(f"   [TeamChannel] Ready (P2P con prioridades). Secondary: {other_dir}")
    return channel


def teardown(flow_manager):
    flow_manager._team_channel = None


def _on_code_review(sender: str, message: str, priority: float):
    """Callback cuando se recibe una revisión de código."""
    print(f"   [TeamChannel] Revisión de código de {sender} (prioridad {priority:.1f})")


def _on_director_feedback(sender: str, message: str, priority: float):
    """Callback cuando el director envía feedback."""
    print(f"   [TeamChannel] Feedback de director {sender}: {message[:100]}")