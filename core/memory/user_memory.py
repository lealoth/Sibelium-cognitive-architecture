import json
from pathlib import Path
from datetime import datetime

from config import USERS_DIR
from core.llm import LLMModel


class UserMemory:
    """Memoria de usuario multi-sesión.
    
    Cada usuario/sesión tiene su propia carpeta bajo entity_data/memory/users/{user_id}/
    con profile.json y history.json independientes.
    """
    
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.user_dir = USERS_DIR / user_id
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.user_dir / "profile.json"
        self._ensure_profile_exists()

    def _ensure_profile_exists(self):
        """Crea el perfil por defecto si no existe."""
        if not self.path.exists():
            self.save_profile(self._default_profile())

    def load_profile(self) -> dict:
        """Carga el perfil del usuario desde disco."""
        if self.path.exists() and self.path.read_text(encoding="utf-8").strip():
            try:
                profile = json.loads(self.path.read_text(encoding="utf-8"))
                # Limpiar historial_clave de entradas vacías
                if "historial_clave" in profile:
                    profile["historial_clave"] = [
                        entry for entry in profile["historial_clave"]
                        if any(v for v in entry.get("datos_extraidos", {}).values() 
                            if v and v not in ["", "No revelado", "No revelada", "Unknown", None])
                    ]
                return profile
            except:
                pass
        return self._default_profile()

    def _default_profile(self) -> dict:
        return {
            "datos_personales": {
                "nombre": None,
                "edad": None,
                "ubicacion": None,
                "ocupacion": None,
                "descripcion_fisica": None
            },
            "relacion": {
                "nivel_confianza": 0.5,
                "tipo_relacion": "nuevo",
                "tiempo_conocido": "0 días",
                "ultimo_contacto": None
            },
            "comportamiento_observado": {
                "estilo": "",
                "actitud": "",
                "humor": "",
                "temas_interes": "",
                "impresion_general": "",
                "patrones": []
            },
            "historial_clave": []
        }

    def save_profile(self, profile: dict):
        """Guarda el perfil del usuario en disco."""
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_profile(self, user_message: str, analysis: dict) -> dict:
        profile = self.load_profile()
        now = datetime.now().isoformat()
        
        profile["relacion"]["ultimo_contacto"] = now
        
        nuevos_datos = self._extract_personal_data(user_message)
        nuevos_datos = self._filter_entity_names(nuevos_datos)
        profile = self._resolve_contradiction(nuevos_datos, profile)
        
        for campo, valor in nuevos_datos.items():
            if valor is not None and valor != profile["datos_personales"].get(campo):
                profile["datos_personales"][campo] = valor
        
        datos_reales = {k: v for k, v in nuevos_datos.items() if v is not None}
        if datos_reales:
            ultimo = profile["historial_clave"][-1] if profile["historial_clave"] else None
            if not ultimo or ultimo.get("datos_extraidos") != datos_reales:
                profile["historial_clave"].append({
                    "fecha": now,
                    "datos_extraidos": datos_reales
                })
                if len(profile["historial_clave"]) > 10:
                    profile["historial_clave"] = profile["historial_clave"][-10:]
        
        self.save_profile(profile)
        return profile

    def _extract_personal_data(self, message: str) -> dict:
        prompt = f"""Extrae SOLO datos personales EXPLÍCITOS del mensaje.
    Si el mensaje no contiene información personal clara, devuelve campos null.

    msg: "{message[:300]}"

    Reglas:
    - name: nombre propio o apodo, máximo 20 caracteres. No frases.
    - age: número o null
    - location: ciudad, país o null. No frases largas.
    - occupation: profesión o null. Máximo 30 caracteres.
    - physical_desc: descripción física breve o null. Máximo 40 caracteres.

    Responde SOLO JSON:
    {{"name": "...", "age": ..., "location": "...", "occupation": "...", "physical_desc": "..."}}"""
        
        try:
            llm = LLMModel.get_instance()
            result = llm.generate(prompt, temperature=0.1, max_tokens=80, purpose="extraer_datos_usuario")
            
            import re as _re
            json_match = _re.search(r'\{.*\}', result, _re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                return self._validate_extracted_data(data)
        except:
            pass
        
        return {"nombre": None, "edad": None, "ubicacion": None, "ocupacion": None, "descripcion_fisica": None}


    def _validate_extracted_data(self, data: dict) -> dict:
        """Filtra datos extraídos que no parecen válidos estructuralmente."""
        result = {"nombre": None, "edad": None, "ubicacion": None, "ocupacion": None, "descripcion_fisica": None}
        
        nombre = (data.get("name") or "").strip()
        if nombre and len(nombre) >= 2 and len(nombre) <= 20 and len(nombre.split()) <= 2:
            result["nombre"] = nombre
        
        edad = data.get("age")
        if isinstance(edad, (int, float)) and 1 < edad < 120:
            result["edad"] = int(edad)
        
        ubicacion = (data.get("location") or "").strip()
        if ubicacion and len(ubicacion) >= 2 and len(ubicacion) <= 40 and len(ubicacion.split()) <= 3:
            result["ubicacion"] = ubicacion
        
        ocupacion = (data.get("occupation") or "").strip()
        if ocupacion and len(ocupacion) >= 2 and len(ocupacion) <= 30 and len(ocupacion.split()) <= 3:
            result["ocupacion"] = ocupacion
        
        desc = (data.get("physical_desc") or "").strip()
        if desc and len(desc) >= 2 and len(desc) <= 40 and len(desc.split()) <= 5:
            result["descripcion_fisica"] = desc
        
        return result

    def update_perception(self, perception_data: dict):
        """Actualiza la percepción subjetiva del usuario."""
        profile = self.load_profile()
        profile["comportamiento_observado"].update(perception_data)
        self.save_profile(profile)

    def reset_profile(self):
        """Elimina el perfil del usuario y crea uno nuevo por defecto."""
        if self.path.exists():
            self.path.unlink()
        return self.load_profile()
    
    def get_history_path(self) -> Path:
        """Devuelve la ruta al archivo de historial de este usuario."""
        return self.user_dir / "history.json"
    
    def _filter_entity_names(self, datos: dict) -> dict:
        """Evita que el nombre de la entidad o sus apodos se asignen al usuario."""
        try:
            from config import PERSONA_FILE, SELF_STATE_FILE
            import json
            
            entity_names = set()
            
            if PERSONA_FILE.exists():
                persona = json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
                name = persona.get("name", "")
                if name:
                    entity_names.add(name.lower().strip())
            
            if SELF_STATE_FILE.exists():
                state = json.loads(SELF_STATE_FILE.read_text(encoding="utf-8"))
                for apodo in state.get("apodos_propios", []):
                    n = apodo.get("nombre", "").lower().strip()
                    if n:
                        entity_names.add(n)
            
            nombre = (datos.get("nombre") or "").lower().strip()
            if nombre and nombre in entity_names:
                datos["nombre"] = None
                print(f"   ⚠️ Nombre de entidad '{nombre}' filtrado del perfil de usuario")
                
        except:
            pass
        
        return datos
    
    def _resolve_contradiction(self, new_data: dict, profile: dict) -> dict:
        """Cuando hay conflicto entre datos nuevos y existentes."""
        for campo, nuevo_valor in new_data.items():
            if not nuevo_valor:
                continue
            viejo_valor = profile.get("datos_personales", {}).get(campo)
            if viejo_valor and viejo_valor != nuevo_valor:
                if "correcciones" not in profile:
                    profile["correcciones"] = []
                profile["correcciones"].append({
                    "campo": campo,
                    "valor_anterior": viejo_valor,
                    "valor_nuevo": nuevo_valor,
                    "fecha": datetime.now().isoformat(),
                    "fuente": "correccion_explicita"
                })
                profile["datos_personales"][campo] = nuevo_valor
        return profile