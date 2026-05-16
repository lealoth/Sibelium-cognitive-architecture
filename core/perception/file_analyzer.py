"""Analizador de archivos para Sibelium."""
import re
from pathlib import Path
from PIL import Image
import torch
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

    def _init_blip(self):
        try:
            print("Cargando BLIP para análisis de imágenes...")
            self.blip_processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-base"
            )
            self.blip_model = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-base"
            )
            print("BLIP cargado correctamente.")
        except Exception as e:
            print(f"⚠️ No se pudo cargar BLIP: {e}")

    def _init_whisper(self):
        if self.whisper_model is not None:
            return
        try:
            import whisper
            print("Cargando Whisper para análisis de audio...")
            self.whisper_model = whisper.load_model("base")
            print("Whisper cargado correctamente.")
        except ImportError:
            print("⚠️ Whisper no instalado. Ejecuta: pip install openai-whisper")
        except Exception as e:
            print(f"⚠️ No se pudo cargar Whisper: {e}")

    def analyze(self, file_path: str, llm=None) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"type": "error", "content": "Archivo no encontrado."}
        ext = path.suffix.lower()
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
            return self._analyze_image(path, llm)
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
            return {"type": "unknown", "content": f"Tipo de archivo no soportado: {ext}"}

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
            except:
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

    def _analyze_basic(self, path, content, ext, llm):
        if llm and len(content) > 500:
            prompt = f"Resume este archivo en 2-3 frases:\n\n{content[:3000]}"
            summary = llm.generate(prompt, temperature=0.3, max_tokens=150, purpose="interpretar")
            return {"type": "text", "file": path.name, "content": content[:5000], "summary": summary}
        return {"type": "text", "file": path.name, "content": content[:5000]}

    def _analyze_detailed(self, path, content, lines, ext, llm):
        functions = re.findall(r'^\s*def\s+(\w+)\s*\(', content, re.MULTILINE)
        classes = re.findall(r'^\s*class\s+(\w+)', content, re.MULTILINE)
        imports = [l.strip() for l in lines if l.startswith('import ') or l.startswith('from ')][:10]
        result = {
            "type": "text",
            "file": path.name,
            "lines": len(lines),
            "structure": {
                "classes": classes,
                "functions": functions[:20],
                "imports": imports
            }
        }
        if llm:
            structure_text = f"Clases: {', '.join(classes) if classes else 'ninguna'}\nFunciones: {', '.join(functions[:15])}\nImports: {', '.join(imports[:5])}"
            prompt = f"Describe el propósito y lógica de este archivo basado en su estructura:\n\n{structure_text}\n\nPrimeras líneas:\n{content[:2000]}"
            result["summary"] = llm.generate(prompt, temperature=0.3, max_tokens=200, purpose="interpretar")
        return result

    def _analyze_exhaustive(self, path, content, lines, ext, llm):
        sections = []
        current_section = {"name": "header", "start": 1, "end": 1}
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('def ') or line.strip().startswith('class '):
                if current_section["name"] != "header":
                    current_section["end"] = i - 1
                    sections.append(current_section)
                current_section = {"name": line.strip()[:80], "start": i, "end": i}
        current_section["end"] = len(lines)
        sections.append(current_section)
        result = {
            "type": "text",
            "file": path.name,
            "lines": len(lines),
            "sections": sections,
            "content_preview": content[:1000]
        }
        if llm:
            sections_text = "\n".join([f"Líneas {s['start']}-{s['end']}: {s['name']}" for s in sections[:30]])
            prompt = f"""Mapa del archivo {path.name} ({len(lines)} líneas):

{sections_text}

Primeras líneas:
{content[:1500]}

Proporciona un análisis estructurado: propósito general, funciones clave, dependencias visibles, y posibles puntos de mejora."""
            result["analysis"] = llm.generate(prompt, temperature=0.3, max_tokens=400, purpose="analizar_imagen")
        return result

    def _analyze_image(self, path: Path, llm=None) -> dict:
        if self.blip_model is None:
            self._init_blip()
            return {"type": "image", "content": "Analizador de imágenes no disponible."}
        try:
            image = Image.open(path).convert("RGB")
            inputs = self.blip_processor(image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.blip_model.generate(**inputs, max_length=100, num_beams=5)
            description = self.blip_processor.decode(outputs[0], skip_special_tokens=True)
            result = {"type": "image", "description": description, "file": path.name}
            if llm:
                enhanced = self._enhance_image_description(description, llm, path.name)
                result["interpretation"] = enhanced
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
        prompt = f"""Analiza esta descripción de imagen generada automáticamente:

"{blip_description}"

La imagen es de tipo: {tipo}.
{ 'Si es una ilustración o dibujo, descríbela como expresión artística, no como algo real. Compárala con la realidad solo para entender el concepto.' if tipo != 'fotografía del mundo real' else '' }
Proporciona una descripción más detallada y natural. No menciones que es un dibujo o IA a menos que sea relevante.
Describe colores, formas, personas, objetos, ambiente y cualquier detalle relevante.
Escribe en español, en 3-5 oraciones."""
        return llm.generate(prompt, temperature=0.5, max_tokens=150, purpose="analizar_imagen")

    def _analyze_text(self, path: Path) -> dict:
        try:
            content = path.read_text(encoding="utf-8")[:5000]
            return {"type": "text", "content": content, "file": path.name}
        except Exception as e:
            return {"type": "error", "content": f"Error leyendo archivo: {e}"}

    def _analyze_pdf(self, path: Path) -> dict:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            text = " ".join([page.extract_text() or "" for page in reader.pages])[:5000]
            return {"type": "document", "content": text, "file": path.name}
        except ImportError:
            return {"type": "error", "content": "PyPDF2 no instalado. Ejecuta: pip install PyPDF2"}
        except Exception as e:
            return {"type": "error", "content": f"Error leyendo PDF: {e}"}

    def _analyze_code(self, path: Path) -> dict:
        try:
            content = path.read_text(encoding="utf-8")[:5000]
            return {"type": "code", "content": content, "file": path.name, "language": path.suffix[1:]}
        except Exception as e:
            return {"type": "error", "content": f"Error leyendo código: {e}"}

    def _analyze_audio(self, path: Path, llm=None) -> dict:
        self._init_whisper()
        if self.whisper_model is None:
            return {"type": "error", "content": "Whisper no está disponible."}
        try:
            result = self.whisper_model.transcribe(str(path))
            transcription = result.get("text", "").strip()
            if not transcription:
                return {"type": "audio", "content": "No se detectó voz en el audio.", "file": path.name}
            audio_result = {"type": "audio", "transcription": transcription, "file": path.name, "language": result.get("language", "desconocido")}
            if llm:
                prompt = f"""Se ha transcrito el siguiente audio:

"{transcription[:1500]}"

Analiza el contenido de esta transcripción. ¿De qué trata? ¿Qué emociones o intenciones percibes?
Responde en español, en 2-4 oraciones."""
                audio_result["interpretation"] = llm.generate(prompt, temperature=0.5, max_tokens=120, purpose="analizar_audio")
            return audio_result
        except Exception as e:
            return {"type": "error", "content": f"Error transcribiendo audio: {e}"}

    def _analyze_video(self, path: Path, llm=None) -> dict:
        try:
            import cv2
        except ImportError:
            return {"type": "error", "content": "OpenCV no instalado. Ejecuta: pip install opencv-python"}
        
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                return {"type": "error", "content": "No se pudo abrir el video."}
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            frame_interval = max(1, int(fps * 3))
            max_frames = 10
            descriptions = []
            frame_count = 0
            analyzed = 0
            while analyzed < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_count % frame_interval == 0:
                    import tempfile
                    tmp_suffix = f"_frame_{analyzed}.jpg"
                    with tempfile.NamedTemporaryFile(suffix=tmp_suffix, delete=False) as f:
                        temp_path = Path(f.name)
                    try:
                        cv2.imwrite(str(temp_path), frame)
                        result = self._analyze_image(temp_path, llm)
                        desc = result.get("interpretation", result.get("description", ""))
                        if desc:
                            descriptions.append(desc)
                    finally:
                        temp_path.unlink(missing_ok=True)
                    analyzed += 1
                frame_count += 1
            video_result = {"type": "video", "file": path.name, "duration_seconds": round(duration, 1), "frames_analyzed": analyzed, "descriptions": descriptions}
            if llm and descriptions:
                prompt = f"""Se analizó un video de {round(duration)} segundos. 
    Descripciones de fotogramas clave:
    {chr(10).join([f'{i+1}. {d}' for i, d in enumerate(descriptions)])}

    Genera un resumen narrativo de lo que sucede en el video.
    Responde en español, en 3-5 oraciones."""
                video_result["narrative"] = llm.generate(prompt, temperature=0.5, max_tokens=150, purpose="analizar_video")
            return video_result
        except Exception as e:
            return {"type": "error", "content": f"Error analizando video: {e}"}
        finally:
            cap.release()