"""Sistema de andamiaje cognitivo para Sibelium.
Determina cuánto apoyo necesita la Entidad para generar pensamiento crítico."""
import json
from pathlib import Path
from datetime import datetime
from config import SCAFFOLDING_FILE

class ScaffoldingManager:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if SCAFFOLDING_FILE.exists():
            try:
                return json.loads(SCAFFOLDING_FILE.read_text(encoding="utf-8"))
            except:
                pass
        return {
            "explorations_by_type": {},
            "patterns_detected": [],
            "critical_questions_count": 0,
            "autonomous_questions_count": 0,
            "last_assessment": None
        }

    def _save(self):
        SCAFFOLDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCAFFOLDING_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def register_exploration(self, file_type: str, filename: str, result: dict):
        if file_type not in self.data["explorations_by_type"]:
            self.data["explorations_by_type"][file_type] = {
                "count": 0,
                "filenames": [],
                "first_exploration": datetime.now().isoformat(),
                "last_exploration": None
            }
        self.data["explorations_by_type"][file_type]["count"] += 1
        self.data["explorations_by_type"][file_type]["filenames"].append(filename)
        self.data["explorations_by_type"][file_type]["last_exploration"] = datetime.now().isoformat()
        self._save()

    def needs_critical_prompt(self, file_type: str, result: dict) -> str:
        type_data = self.data["explorations_by_type"].get(file_type, {"count": 0})
        count = type_data.get("count", 0)
        if count <= 1:
            return "full"
        if count <= 5:
            return "light"
        if self._is_unusual(result, type_data):
            return "light"
        return "none"

    def _is_unusual(self, result, type_data) -> bool:
        description = result.get("interpretation", result.get("description", ""))
        filename = result.get("file", "")
        detected_type = self._detect_novelty(filename, type_data.get("filenames", []))
        novelty_words = ["inusual", "extraño", "diferente", "nuevo", "raro", "sorprendente"]
        has_novelty = any(word in description.lower() for word in novelty_words)
        return detected_type or has_novelty

    def _detect_novelty(self, filename, known_files):
        prefixes = ["real_", "arte_", "ia_", "hist_", "meme_", "anim_", "dibujo_", "paisaje_"]
        for prefix in prefixes:
            if filename.startswith(prefix):
                same_prefix = [f for f in known_files if f.startswith(prefix)]
                if len(same_prefix) <= 1:
                    return True
        return False

    def register_critical_question(self, was_autonomous: bool = False):
        if was_autonomous:
            self.data["autonomous_questions_count"] += 1
        else:
            self.data["critical_questions_count"] += 1
        self.data["last_assessment"] = datetime.now().isoformat()
        self._save()

    def get_autonomy_ratio(self) -> float:
        total = self.data["critical_questions_count"] + self.data["autonomous_questions_count"]
        if total == 0:
            return 0.0
        return self.data["autonomous_questions_count"] / total

    def should_promote_autonomy(self) -> bool:
        total = self.data["critical_questions_count"] + self.data["autonomous_questions_count"]
        if total < 20:
            return False
        ratio = self.get_autonomy_ratio()
        return ratio >= 0.4