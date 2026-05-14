"""Cargador de mods. Escanea mods/ y registra los disponibles."""
import json
from pathlib import Path
from typing import Dict, List

MODS_DIR = Path(__file__).resolve().parent


class ModInfo:
    def __init__(self, mod_id: str, mod_path: Path, metadata: dict):
        self.id = mod_id
        self.path = mod_path
        self.name = metadata.get("name", mod_id)
        self.version = metadata.get("version", "0.1.0")
        self.description = metadata.get("description", "")
        self.author = metadata.get("author", "")
        self.dependencies = metadata.get("dependencies", [])
        self.enabled = False
        self.instance = None


class ModLoader:
    def __init__(self):
        self.registered: Dict[str, ModInfo] = {}
        self._scan()

    def _scan(self):
        for folder in MODS_DIR.iterdir():
            if not folder.is_dir() or folder.name.startswith('_') or folder.name == '__pycache__':
                continue
            
            mod_json = folder / "mod.json"
            if not mod_json.exists():
                continue
            
            try:
                metadata = json.loads(mod_json.read_text(encoding="utf-8"))
                self.registered[folder.name] = ModInfo(folder.name, folder, metadata)
            except Exception as e:
                print(f"   [!] Error cargando mod {folder.name}: {e}")

    def list_available(self) -> List[dict]:
        return [
            {
                "id": m.id, "name": m.name, "version": m.version,
                "description": m.description, "enabled": m.enabled
            }
            for m in self.registered.values()
        ]

    def enable(self, mod_id: str, flow_manager=None) -> bool:
        if mod_id not in self.registered:
            print(f"   [!] Mod no encontrado: {mod_id}")
            return False
        
        mod = self.registered[mod_id]
        
        for dep in mod.dependencies:
            if dep not in self.registered or not self.registered[dep].enabled:
                print(f"   [!] Dependencia faltante: {dep}")
                return False
        
        try:
            main_file = mod.path / "main.py"
            if main_file.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    f"mods.{mod_id}.main", str(main_file)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if flow_manager and hasattr(module, 'setup'):
                    mod.instance = module.setup(flow_manager)
            else:
                mod.instance = True
            
            mod.enabled = True
            print(f"   [Mod] Activado: {mod.name} v{mod.version}")
            return True
        except Exception as e:
            print(f"   [!] Error activando mod {mod_id}: {e}")
            return False

    def disable(self, mod_id: str, flow_manager=None) -> bool:
        if mod_id not in self.registered:
            return False
        
        mod = self.registered[mod_id]
        
        try:
            if mod.instance and hasattr(mod.instance, 'teardown'):
                mod.instance.teardown(flow_manager)
            mod.enabled = False
            mod.instance = None
            print(f"   [Mod] Desactivado: {mod.name}")
            return True
        except Exception as e:
            print(f"   [!] Error desactivando mod {mod_id}: {e}")
            return False

    def setup_all(self, enabled_ids: List[str], flow_manager=None):
        for mod_id in enabled_ids:
            self.enable(mod_id, flow_manager)


loader = ModLoader()