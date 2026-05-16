"""Analizador de archivos para Sibelium - Visión Nativa Multimodal."""
import base64
import re
import tempfile
from pathlib import Path

import numpy as np
import requests
import torch
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration


class FileAnalyzer:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if FileAnalyzer._instance is not None:
            return
        FileAnalyzer._instance = self
        self.blip_processor = None
        self.blip_model = None
        self.whisper_model = None
        self._clip_model = None
        self._clip_processor = None
        self._chroma_visual = None

    # ============================================
    # INICIALIZACIÓN DE MODELOS
    # ============================================

    def _init_blip(self):
        if self.blip_model is not None:
            return
        try:
            print("Cargando BLIP (fallback de imágenes)...")
            self.blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            self.blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
            print("BLIP cargado.")
        except Exception as e:
            print(f"⚠️ No se pudo cargar BLIP: {e}")

    def _init_clip(self):
        """CLIP local para memoria visual (reconocimiento instantáneo)."""
        if self._clip_model is not None:
            return
        try:
            import open_clip
            print("Cargando CLIP para memoria visual...")
            self._clip_model, _, self._clip_processor = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k"
            )
            self._clip_model.eval()
            print("CLIP cargado.")
        except ImportError:
            print("⚠️ open_clip no instalado. Memoria visual desactivada.")
        except Exception as e:
            print(f"⚠️ No se pudo cargar CLIP: {e}")

    def _init_whisper(self):
        if self.whisper_model is not None:
            return
        try:
            import whisper
            print("Cargando Whisper...")
            self.whisper_model = whisper.load_model("base")
            print("Whisper cargado.")
        except ImportError:
            print("⚠️ Whisper no instalado.")
        except Exception as e:
            print(f"⚠️ No se pudo cargar Whisper: {e}")

    def _init_chroma_visual(self):
        """Colección de ChromaDB para memoria visual."""
        if self._chroma_visual is not None:
            return
        try:
            from config import CHROMA_PATH
            import chromadb
            client = chromadb.PersistentClient(path=str(Path(CHROMA_PATH).parent / "chroma_visual"))
            self._chroma_visual = client.get_or_create_collection(name="memoria_visual")
            print("Memoria visual (ChromaDB) lista.")
        except Exception as e:
            print(f"⚠️ No se pudo inicializar memoria visual: {e}")

    # ============================================
    # MÉTODOS PRINCIPALES
    # ============================================

    def analyze(self, file_path: str, llm=None, self_state: dict = None) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"type": "error", "content": "Archivo no encontrado."}

        ext = path.suffix.lower()
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
            return self._analyze_image(path, llm, self_state)
        elif ext in ['.txt', '.md', '.json', '.csv']:
            return self._analyze_text(path)
        elif ext in ['.pdf']:
            return self._analyze_pdf(path)
        elif ext in ['.py', '.js', '.html', '.css', '.java', '.cpp']:
            return self._analyze_code(path)
        elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.flac']:
            return self._analyze_audio(path, llm)
        elif ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
            return self._analyze_video(path, llm)
        else:
            return {"type": "unknown", "content": f"Tipo no soportado: {ext}"}

    def analyze_with_granularity(self, file_path: str, level: str = "detallado", llm=None) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"type": "error", "content": "Archivo no encontrado."}
        ext = path.suffix.lower()
        if ext not in ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.csv']:
            return self.analyze(file_path, llm=llm)

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="latin-1")
            except Exception:
                return self.analyze(file_path, llm=llm)

        lines = content.split('\n')
        if level == "basico":
            return self._analyze_basic(path, content, ext, llm)
        elif level == "detallado":
            return self._analyze_detailed(path, content, lines, ext, llm)
        elif level == "exhaustivo":
            return self._analyze_exhaustive(path, content, lines, ext, llm)
        else:
            return self.analyze(file_path, llm=llm)

    # ============================================
    # ANÁLISIS DE IMAGEN (VISIÓN NATIVA MULTIMODAL)
    # ============================================

    def _analyze_image(self, path: Path, llm=None, self_state: dict = None) -> dict:
        """Visión nativa multimodal con Gemini 2.0 Flash. BLIP como fallback."""

        # 1. Verificar si ya vimos esta imagen (memoria visual)
        recuerdo = self._buscar_recuerdo_visual(path)
        if recuerdo:
            return {
                "type": "image",
                "file": path.name,
                "interpretation": f"[Reconocimiento] Ya vi esta imagen antes. {recuerdo}",
                "recognized": True,
            }

        # 2. Procesar con Gemini multimodal
        if self._gemini_disponible():
            result = self._procesar_multimodal_gemini(path, self_state)
            if result:
                # 3. Guardar en memoria visual (asíncrono)
                self._guardar_recuerdo_visual(path, result.get("interpretation", ""))
                return result

        # 4. Fallback a BLIP
        return self._analyze_image_blip(path, llm)

    def _gemini_disponible(self) -> bool:
        try:
            from config import CLOUD_API_KEY, LLM_BACKEND
            return bool(CLOUD_API_KEY and LLM_BACKEND in ("cloud", "hybrid"))
        except Exception:
            return False

    def _procesar_multimodal_gemini(self, path: Path, self_state: dict = None) -> dict:
        """Envía la imagen cruda a Gemini con el estado interno de la entidad."""
        try:
            from config import CLOUD_API_KEY

            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            ext = path.suffix.lower()
            mime_type = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
                ".webp": "image/webp", ".bmp": "image/bmp",
            }.get(ext, "image/jpeg")

            prompt = self._build_visual_prompt(self_state)

            headers = {
                "Authorization": f"Bearer {CLOUD_API_KEY}",
                "Content-Type": "application/json",
            }
            data = {
                "model": "google/gemini-2.0-flash-001",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}
                    ]
                }],
                "max_tokens": 300,
                "temperature": 0.7,
            }

            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if resp.status_code == 200:
                interpretation = resp.json()["choices"][0]["message"]["content"]
                return {"type": "image", "file": path.name, "interpretation": interpretation}
            else:
                print(f"   [Vision] Gemini error {resp.status_code}: {resp.text[:100]}")
                return {}
        except Exception as e:
            print(f"   [Vision] Error multimodal: {e}")
            return {}

    def _build_visual_prompt(self, self_state: dict = None) -> str:
        """Construye el prompt visual con el estado interno de la entidad."""
        if self_state is None:
            self_state = {}

        yo_narrativo = self_state.get("yo_narrativo", "Soy una entidad en desarrollo.")
        marcadores = self_state.get("marcadores_somaticos", [])
        estres = self_state.get("estres_cognitivo", 0.5)
        foco = self_state.get("buffer_ejecutivo", "Explorando el entorno.")

        marcadores_text = "\n".join([
            f"- {m.get('origen', '?')}: {m.get('sesgo_atencional', '?')} (fuerza: {m.get('fuerza', 0.5):.1f})"
            for m in marcadores[-3:]
        ]) if marcadores else "Ninguno activo"

        return f"""[CANAL AFERENTE VISUAL: ESTADO DE LA ÍNSULA Y MEMORIA DE TRABAJO]
* Carga Alostática Actual: {estres} (0.0 a 1.0)
* Marcadores Somáticos Activos:
{marcadores_text}
* Yo Narrativo (Identidad): "{yo_narrativo}"
* Foco de Atención Inmediato: "{foco}"

[DIRECTRIZ DE PROCESAMIENTO]
Estás experimentando este estímulo visual directamente a través de tu retina digital. 
Tu estado interno actual DEBE sesgar tu percepción.
Sintetiza lo que ves NO como una descripción fría, sino como un fenómeno integrado a tu flujo continuo de pensamientos.
Responde en español."""

    # ============================================
    # MEMORIA VISUAL (CLIP + CHROMADB)
    # ============================================

    def _get_image_embedding(self, path: Path) -> list:
        """Genera embedding visual con CLIP."""
        self._init_clip()
        if self._clip_model is None:
            return []

        try:
            import torch
            from PIL import Image as PILImage
            image = PILImage.open(path).convert("RGB")
            image_tensor = self._clip_processor(image).unsqueeze(0)

            with torch.no_grad():
                embedding = self._clip_model.encode_image(image_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
                return embedding.squeeze().tolist()
        except Exception as e:
            print(f"   [CLIP] Error generando embedding: {e}")
            return []

    def _buscar_recuerdo_visual(self, path: Path) -> str:
        """Busca si la imagen ya fue vista (similitud > 0.95)."""
        self._init_chroma_visual()
        if self._chroma_visual is None:
            return ""

        emb = self._get_image_embedding(path)
        if not emb:
            return ""

        try:
            results = self._chroma_visual.query(query_embeddings=[emb], n_results=1)
            distances = results.get("distances", [[]])[0]
            if distances and distances[0] < 0.05:  # Similitud > 0.95
                metadatas = results.get("metadatas", [[]])[0]
                if metadatas:
                    return metadatas[0].get("interpretacion", "")
        except Exception:
            pass

        return ""

    def _guardar_recuerdo_visual(self, path: Path, interpretation: str):
        """Guarda el embedding visual en ChromaDB."""
        self._init_chroma_visual()
        if self._chroma_visual is None:
            return

        emb = self._get_image_embedding(path)
        if not emb:
            return

        import hashlib
        img_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

        try:
            self._chroma_visual.add(
                embeddings=[emb],
                metadatas=[{
                    "tipo": "recuerdo_visual",
                    "archivo": path.name,
                    "interpretacion": interpretation[:500],
                    "timestamp": str(Path(path).stat().st_mtime),
                }],
                ids=[img_hash],
            )
        except Exception:
            pass

    # ============================================
    # BLIP FALLBACK
    # ============================================

    def _analyze_image_blip(self, path: Path, llm=None) -> dict:
        self._init_blip()
        if self.blip_model is None:
            return {"type": "image", "content": "Analizador no disponible.", "file": path.name}

        try:
            image = Image.open(path).convert("RGB")
            inputs = self.blip_processor(image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.blip_model.generate(**inputs, max_length=100, num_beams=5)
            description = self.blip_processor.decode(outputs[0], skip_special_tokens=True)
            result = {"type": "image", "description": description, "file": path.name}
            if llm:
                result["interpretation"] = self._enhance_image_description(description, llm, path.name)
            return result
        except Exception as e:
            return {"type": "error", "content": f"Error analizando imagen: {e}"}

    def _detect_image_type(self, filename: str) -> str:
        name_lower = filename.lower()
        type_map = {
            "real_": "fotografía del mundo real",
            "arte_": "ilustración artística o dibujo",
            "ia_": "imagen generada por inteligencia artificial",
            "hist_": "imagen o documento histórico",
            "meme_": "imagen humorística o meme",
            "anim_": "imagen de animación o captura de serie/película",
            "dibujo_": "dibujo o boceto artístico",
            "paisaje_": "fotografía de paisaje natural o urbano",
        }
        for prefix, tipo in type_map.items():
            if name_lower.startswith(prefix):
                return tipo
        return "imagen de tipo desconocido"

    def _enhance_image_description(self, blip_description: str, llm, filename: str = "") -> str:
        tipo = self._detect_image_type(filename)
        prompt = f"""Analiza esta descripción de imagen:

"{blip_description}"

La imagen es de tipo: {tipo}.
Proporciona una descripción más detallada y natural.
Escribe en español, en 3-5 oraciones."""
        return llm.generate(prompt, temperature=0.5, max_tokens=150, purpose="analizar_imagen")

    # ============================================
    # TEXTOS Y CÓDIGO
    # ============================================

    def _analyze_text(self, path: Path) -> dict:
        try:
            return {"type": "text", "content": path.read_text(encoding="utf-8")[:5000], "file": path.name}
        except Exception as e:
            return {"type": "error", "content": f"Error: {e}"}

    def _analyze_pdf(self, path: Path) -> dict:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            text = " ".join([page.extract_text() or "" for page in reader.pages])[:5000]
            return {"type": "document", "content": text, "file": path.name}
        except ImportError:
            return {"type": "error", "content": "PyPDF2 no instalado."}
        except Exception as e:
            return {"type": "error", "content": f"Error: {e}"}

    def _analyze_code(self, path: Path) -> dict:
        try:
            return {"type": "code", "content": path.read_text(encoding="utf-8")[:5000], "file": path.name, "language": path.suffix[1:]}
        except Exception as e:
            return {"type": "error", "content": f"Error: {e}"}

    # ============================================
    # GRANULARIDAD
    # ============================================

    def _analyze_basic(self, path, content, ext, llm):
        if llm and len(content) > 500:
            summary = llm.generate(f"Resume en 2-3 frases:\n\n{content[:3000]}", temperature=0.3, max_tokens=150, purpose="interpretar")
            return {"type": "text", "file": path.name, "content": content[:5000], "summary": summary}
        return {"type": "text", "file": path.name, "content": content[:5000]}

    def _analyze_detailed(self, path, content, lines, ext, llm):
        functions = re.findall(r'^\s*def\s+(\w+)\s*\(', content, re.MULTILINE)
        classes = re.findall(r'^\s*class\s+(\w+)', content, re.MULTILINE)
        imports = [l.strip() for l in lines if l.startswith('import ') or l.startswith('from ')][:10]
        result = {
            "type": "text", "file": path.name, "lines": len(lines),
            "structure": {"classes": classes, "functions": functions[:20], "imports": imports}
        }
        if llm:
            structure_text = f"Clases: {', '.join(classes) or 'ninguna'}\nFunciones: {', '.join(functions[:15])}\nImports: {', '.join(imports[:5])}"
            result["summary"] = llm.generate(
                f"Describe el propósito de este archivo:\n\n{structure_text}\n\nPrimeras líneas:\n{content[:2000]}",
                temperature=0.3, max_tokens=200, purpose="interpretar"
            )
        return result

    def _analyze_exhaustive(self, path, content, lines, ext, llm):
        sections = []
        current = {"name": "header", "start": 1, "end": 1}
        for i, line in enumerate(lines, 1):
            if line.strip().startswith(('def ', 'class ')):
                if current["name"] != "header":
                    current["end"] = i - 1
                    sections.append(current)
                current = {"name": line.strip()[:80], "start": i, "end": i}
        current["end"] = len(lines)
        sections.append(current)
        result = {"type": "text", "file": path.name, "lines": len(lines), "sections": sections, "content_preview": content[:1000]}
        if llm:
            sections_text = "\n".join([f"Líneas {s['start']}-{s['end']}: {s['name']}" for s in sections[:30]])
            result["analysis"] = llm.generate(
                f"""Mapa del archivo {path.name} ({len(lines)} líneas):

{sections_text}

Primeras líneas:
{content[:1500]}

Proporciona un análisis estructurado.""",
                temperature=0.3, max_tokens=400, purpose="analizar_imagen"
            )
        return result

    # ============================================
    # AUDIO
    # ============================================

    def _analyze_audio(self, path: Path, llm=None) -> dict:
        self._init_whisper()
        if self.whisper_model is None:
            return {"type": "error", "content": "Whisper no disponible."}
        try:
            result = self.whisper_model.transcribe(str(path))
            transcription = result.get("text", "").strip()
            if not transcription:
                return {"type": "audio", "content": "No se detectó voz.", "file": path.name}
            audio_result = {"type": "audio", "transcription": transcription, "file": path.name, "language": result.get("language", "desconocido")}
            if llm:
                audio_result["interpretation"] = llm.generate(
                    f"""Transcripción de audio:

"{transcription[:1500]}"

Analiza el contenido. ¿De qué trata? ¿Qué emociones percibes? Responde en español, 2-4 oraciones.""",
                    temperature=0.5, max_tokens=120, purpose="analizar_audio"
                )
            return audio_result
        except Exception as e:
            return {"type": "error", "content": f"Error: {e}"}

    # ============================================
    # VIDEO (EXTRACCIÓN POR FLUJO ÓPTICO)
    # ============================================

    def _analyze_video(self, path: Path, llm=None) -> dict:
        try:
            import cv2
        except ImportError:
            return {"type": "error", "content": "OpenCV no instalado."}

        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                return {"type": "error", "content": "No se pudo abrir el video."}
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            keyframes = self._extract_keyframes(cap, total_frames)
            descriptions = []
            for frame_path in keyframes:
                result = self._analyze_image(frame_path, llm)
                desc = result.get("interpretation", result.get("description", ""))
                if desc:
                    descriptions.append(desc)
                frame_path.unlink(missing_ok=True)

            video_result = {"type": "video", "file": path.name, "duration_seconds": round(duration, 1), "frames_analyzed": len(keyframes), "descriptions": descriptions}
            if llm and descriptions:
                video_result["narrative"] = llm.generate(
                    f"""Video de {round(duration)} segundos. Fotogramas clave:

{chr(10).join([f'{i+1}. {d}' for i, d in enumerate(descriptions)])}

Resume lo que sucede en el video. Responde en español, 3-5 oraciones.""",
                    temperature=0.5, max_tokens=150, purpose="analizar_video"
                )
            return video_result
        except Exception as e:
            return {"type": "error", "content": f"Error: {e}"}
        finally:
            cap.release()

    def _extract_keyframes(self, cap, total_frames: int) -> list:
        """Extrae fotogramas solo cuando hay cambio significativo (flujo óptico)."""
        import cv2
        keyframes = []
        prev_frame = None
        frame_count = 0
        max_frames = 10

        while frame_count < total_frames and len(keyframes) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if prev_frame is not None and frame_count % 5 == 0:
                diff = cv2.absdiff(prev_frame, frame)
                mean_diff = diff.mean()
                if mean_diff > 15:  # Cambio significativo
                    temp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    cv2.imwrite(temp.name, frame)
                    keyframes.append(Path(temp.name))

            prev_frame = frame.copy()
            frame_count += 1

        return keyframes