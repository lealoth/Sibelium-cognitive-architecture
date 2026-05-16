"""
Sibelium Cognitive Assistant - API Server
==========================================
Endpoints principales:
  POST /api/chat          - Enviar mensaje a la Entidad
  POST /api/session/create - Crear nueva sesión
  GET  /api/sessions      - Listar sesiones
  GET  /api/state         - Estado cognitivo actual
  GET  /api/history       - Historial de conversación
  GET  /api/thoughts/last - Últimos pensamientos
  POST /api/reset         - Reiniciar memoria
  POST /api/upload        - Subir archivo
  POST /api/voice-message - Mensaje de voz
  POST /api/heartbeat     - Latido del frontend
  GET  /api/user/online   - Estado del usuario
  GET  /api/nexus/pending - Mensajes proactivos
"""

import json
import uuid
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import hashlib

from config import ENTITY_DATA_DIR, USERS_DIR
from core.cognitive_loop import CognitiveLoop

from mods.loader import loader
from config import ENABLED_MODS

# ============================================
# CONFIGURACIÓN INICIAL
# ============================================

UPLOADS_DIR = ENTITY_DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    '.txt', '.md', '.pdf', '.json', '.csv',
    '.py', '.js', '.html', '.css',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
    '.mp3', '.wav', '.ogg', '.m4a', '.flac'
}

app = FastAPI(title="Sibelium Cognitive Assistant")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# No-cache para archivos estáticos
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/css/") or path.startswith("/js/") or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ============================================
# MODELOS
# ============================================

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class SessionCreateRequest(BaseModel):
    name: str = "Nueva sesión"

class ChatResponse(BaseModel):
    response: str
    thought_history: list
    cognitive_state: dict


# ============================================
# GESTIÓN DE SESIONES
# ============================================

# Diccionario en memoria: session_id → CognitiveLoop
sessions: dict[str, CognitiveLoop] = {}


def get_or_create_loop(session_id: str) -> CognitiveLoop:
    """Obtiene el CognitiveLoop de una sesión o lo crea si no existe."""
    if session_id not in sessions:
        session_dir = USERS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        meta_path = session_dir / "meta.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps({
                "name": session_id[:8],
                "created": datetime.now().isoformat(),
                "private": False
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        
        loop = CognitiveLoop(user_id=session_id, start_flow=False)
        loader.setup_all(ENABLED_MODS, loop.flow_manager)
        loop.flow_manager.start()
        sessions[session_id] = loop
        print(f"[Session] Sesión cargada: {session_id}")
    
    return sessions[session_id]


# ============================================
# INICIALIZACIÓN DEL SISTEMA COGNITIVO
# ============================================

print("=" * 60)
print("🧠 Inicializando Sibelium Cognitive Assistant...")
print("=" * 60)

# Precargar sesión default al inicio
_default_loop = get_or_create_loop("default")
last_heartbeat = None

print("✅ Sistema cognitivo creado (flujo detenido).")


# ============================================
# EVENTOS DE STARTUP
# ============================================

@app.on_event("startup")
async def startup_event():
    """Precarga modelos y arranca el flujo cuando todo está listo."""
    print("📦 Precargando modelos...")
    
    from core.llm import LLMModel
    llm = LLMModel.get_instance()
    llm.load_model()
    print("   ✅ LLMs cargados")
    
    from core.perception.file_analyzer import FileAnalyzer
    FileAnalyzer.get_instance()
    print("   ✅ BLIP cargado")
    
    # Arrancar flujo de la sesión default (las demás se arrancan al crearse)
    _default_loop.flow_manager.start()
    print("   ✅ FlowManager arrancado")
    
    print("=" * 60)
    print("🚀 Servidor listo en http://127.0.0.1:8000")
    print("=" * 60)


# ============================================
# ENDPOINTS DE SESIÓN
# ============================================

@app.post("/api/session/create")
async def create_session(request: SessionCreateRequest):
    """Crea una nueva sesión y devuelve su ID."""
    session_id = uuid.uuid4().hex[:12]
    session_dir = USERS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    meta_path = session_dir / "meta.json"
    meta_path.write_text(json.dumps({
        "name": request.name,
        "created": datetime.now().isoformat(),
        "private": False
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    
    loop = get_or_create_loop(session_id)
    
    print(f"[Session] Nueva sesión creada: {session_id} ({request.name})")
    return {"session_id": session_id, "name": request.name}


@app.get("/api/sessions")
async def list_sessions():
    """Lista todas las sesiones disponibles."""
    result = []
    if USERS_DIR.exists():
        for session_dir in sorted(USERS_DIR.iterdir(), key=lambda d: d.name):
            if session_dir.is_dir():
                meta_path = session_dir / "meta.json"
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except:
                        pass
                result.append({
                    "session_id": session_dir.name,
                    "name": meta.get("name", session_dir.name[:8]),
                    "created": meta.get("created", ""),
                    "private": meta.get("private", False)
                })
    return {"sessions": result}


@app.post("/api/session/lock")
async def lock_session(request: Request):
    """Protege una sesión con clave."""
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="JSON inválido")
    
    session_id = data.get("session_id", "default")
    password = data.get("password", "")
    
    if len(password) < 3:
        raise HTTPException(status_code=400, detail="Clave demasiado corta")
    
    import hashlib
    session_dir = USERS_DIR / session_id
    meta_path = session_dir / "meta.json"
    
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    meta["private"] = True
    meta["password_hash"] = password_hash
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"[Session] Sesión protegida: {session_id}")
    return {"status": "locked"}


@app.post("/api/session/unlock")
async def unlock_session(request: Request):
    """Desbloquea o quita protección a una sesión."""
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="JSON inválido")
    
    session_id = data.get("session_id", "default")
    password = data.get("password", "")
    remove = data.get("remove", False)
    
    import hashlib
    session_dir = USERS_DIR / session_id
    meta_path = session_dir / "meta.json"
    
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    
    if remove:
        # Quitar protección (ya autenticado por UI)
        meta["private"] = False
        meta.pop("password_hash", None)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "unlocked"}
    
    # Verificar clave
    stored_hash = meta.get("password_hash", "")
    given_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if stored_hash != given_hash:
        raise HTTPException(status_code=403, detail="Clave incorrecta")
    
    return {"status": "unlocked"}

# ============================================
# ENDPOINTS DE CONVERSACIÓN
# ============================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Procesa un mensaje del usuario y retorna la respuesta de la Entidad."""
    log_line()
    print(f"[Chat] Mensaje recibido: {request.message[:100]}...")
    
    try:
        loop = get_or_create_loop(request.session_id)
        result = loop.process(request.message)
        
        if result is None:
            print("[Chat] ❌ Resultado None")
            raise HTTPException(status_code=500, detail="No se pudo generar una respuesta")
        
        if "response" not in result:
            print(f"[Chat] ❌ Falta 'response'. Keys: {list(result.keys())}")
            raise HTTPException(status_code=500, detail="Respuesta inválida del sistema")
        
        response_text = result.get("response", "")
        print(f"[Chat] ✅ Respuesta generada ({len(response_text)} chars)")
        print(f"[Chat] 💬 {response_text[:200]}")
        if len(response_text) > 250:
            print(f"[Chat]    ... ({len(response_text) - 250} chars más)")
            
        return ChatResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Chat] 💥 ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# ============================================
# ENDPOINTS DE ESTADO E HISTORIAL
# ============================================

@app.get("/api/state")
async def get_state(session_id: str = "default"):
    """Estado cognitivo actual de la Entidad."""
    loop = get_or_create_loop(session_id)
    state = loop.get_last_state()
    return state if state else {"status": "empty"}


@app.get("/api/history")
async def get_history(session_id: str = "default"):
    """Historial completo de conversación y pensamientos."""
    loop = get_or_create_loop(session_id)
    return {
        "history": loop.get_history(),
        "thought_history": loop.get_last_thoughts(),
        "cognitive_state": loop.get_last_state(),
    }


@app.get("/api/thoughts/last")
async def get_last_thoughts(session_id: str = "default"):
    """Últimos pensamientos del ciclo actual."""
    loop = get_or_create_loop(session_id)
    return {"thought_history": loop.get_last_thoughts()}


@app.post("/api/reset")
async def reset_endpoint(session_id: str = "default"):
    """Reinicia toda la memoria de la Entidad para esta sesión."""
    print("[System] 🔄 Reiniciando memoria...")
    loop = get_or_create_loop(session_id)
    loop.reset()
    print("[System] ✅ Memoria reiniciada")
    return {"status": "reset"}


# ============================================
# ENDPOINTS DE ARCHIVOS
# ============================================

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), session_id: str = "default"):
    """Sube un archivo para que la entidad lo analice."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {ext}")
    
    file_path = UPLOADS_DIR / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    print(f"[Upload] Archivo recibido: {file.filename} ({len(content)} bytes)")
    
    from core.perception.file_analyzer import FileAnalyzer
    analyzer = FileAnalyzer.get_instance()
    loop = get_or_create_loop(session_id)
    llm = loop.flow_manager.llm if hasattr(loop, 'flow_manager') else None
    result = analyzer.analyze_with_granularity(str(file_path), level="detallado", llm=llm)
    
    print(f"[Upload] ✅ Analizado: {result.get('type', 'unknown')}")
    
    return {
        "filename": file.filename,
        "analysis": result
    }


@app.post("/api/voice-message")
async def voice_message(file: UploadFile = File(...), session_id: str = "default"):
    """Recibe un mensaje de voz, lo transcribe y analiza el tono."""
    temp_path = UPLOADS_DIR / f"voice_{datetime.now().timestamp()}.wav"
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    print(f"[Voice] Audio recibido: {len(content)} bytes")
    
    from core.perception.file_analyzer import FileAnalyzer
    analyzer = FileAnalyzer.get_instance()
    audio_result = analyzer.analyze(str(temp_path))
    
    transcription = audio_result.get("transcription", "")
    loop = get_or_create_loop(session_id)
    
    if transcription:
        llm = loop.flow_manager.llm
        analysis_prompt = f"""Se ha transcrito un mensaje de voz. Analiza las características vocales.

Transcripción: "{transcription}"

Describe en 2-3 oraciones: emoción percibida, tono de voz, algo notable en la expresión.
Respuesta:"""
        
        voice_analysis = llm.generate(analysis_prompt, temperature=0.5, max_tokens=100, purpose="analizar_voz")
    else:
        voice_analysis = "No se detectó voz en el audio."
    
    temp_path.unlink(missing_ok=True)
    
    try:
        user_profile = loop.user_memory.load_profile()
        if "descripcion_voz" not in user_profile:
            user_profile["descripcion_voz"] = {}
        user_profile["descripcion_voz"]["ultimo_analisis"] = {
            "timestamp": datetime.now().isoformat(),
            "tono": voice_analysis[:200],
            "transcripcion": transcription[:100]
        }
        loop.user_memory.save_profile(user_profile)
    except Exception:
        pass
    
    enriched_message = f"[Mensaje de voz]\nTranscripción: \"{transcription}\"\nAnálisis del tono: {voice_analysis}"
    result = loop.process(enriched_message)
    
    print(f"[Voice] ✅ Procesado: \"{transcription[:80]}...\"")
    
    return {
        "transcription": transcription,
        "voice_analysis": voice_analysis,
        "response": result["response"],
        "thought_history": result["thought_history"],
        "cognitive_state": result["cognitive_state"]
    }


# ============================================
# ENDPOINTS DE PRESENCIA
# ============================================

@app.post("/api/heartbeat")
async def heartbeat():
    """Registra que el usuario tiene la página abierta."""
    global last_heartbeat
    last_heartbeat = datetime.now()
    return {"status": "ok"}


@app.get("/api/user/online")
async def is_user_online():
    """¿Está el usuario con la página abierta?"""
    global last_heartbeat
    if last_heartbeat is None:
        return {"online": False}
    elapsed = (datetime.now() - last_heartbeat).total_seconds()
    return {"online": elapsed < 60}


# ============================================
# ENDPOINTS DE LA ENTIDAD (MENSAJES PROACTIVOS)
# ============================================

@app.get("/api/nexus/pending")
async def get_pending_messages(session_id: str = "default"):
    """Obtiene mensajes proactivos de la entidad."""
    loop = get_or_create_loop(session_id)
    if hasattr(loop, 'flow_manager') and loop.flow_manager:
        return {"messages": loop.flow_manager.get_pending_messages()}
    return {"messages": []}

@app.post("/api/nexus/pending/clear")
async def clear_pending_messages(session_id: str = "default"):
    """Limpia los mensajes pendientes."""
    loop = get_or_create_loop(session_id)
    if hasattr(loop, 'flow_manager') and loop.flow_manager:
        loop.flow_manager.clear_pending_messages()
    return {"status": "cleared"}

@app.get("/api/nexus/proactive-stream")
async def proactive_stream(session_id: str = "default"):
    """Streaming de mensajes proactivos usando Server-Sent Events."""
    async def event_generator():
        last_count = 0
        while True:
            loop = get_or_create_loop(session_id)
            if hasattr(loop, 'flow_manager') and loop.flow_manager:
                messages = loop.flow_manager.get_pending_messages()
                if len(messages) > last_count:
                    for msg in messages[last_count:]:
                        yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    last_count = len(messages)
            await asyncio.sleep(5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# ============================================
# DEBUG
# ============================================

@app.get("/debug")
async def debug():
    """Endpoint de diagnóstico."""
    frontend_path = Path("frontend")
    return {
        "files_exist": {
            "index.html": (frontend_path / "index.html").exists(),
            "css/style.css": (frontend_path / "css" / "style.css").exists(),
            "js/api.js": (frontend_path / "js" / "api.js").exists(),
            "js/app.js": (frontend_path / "js" / "app.js").exists(),
            "js/thought_viewer.js": (frontend_path / "js" / "thought_viewer.js").exists(),
        },
        "frontend_path": str(frontend_path),
        "sessions": list(sessions.keys()),
        "active_sessions": len(sessions),
    }


@app.get("/api/metrics")
async def get_metrics(session_id: str = "default"):
    loop = get_or_create_loop(session_id)
    if hasattr(loop.flow_manager, 'llm') and hasattr(loop.flow_manager.llm, 'metrics'):
        return {"summary": loop.flow_manager.llm.metrics.get_summary()}
    return {"summary": "Métricas no disponibles"}

# ============================================
# UTILIDADES
# ============================================

def log_line(char="=", length=60):
    """Imprime una línea separadora en los logs."""
    print(char * length)


# ============================================
# STATIC FILES (SIEMPRE AL FINAL)
# ============================================

frontend_path = Path("frontend")
app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")