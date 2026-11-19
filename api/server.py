"""
Sibelium Cognitive Assistant - API Server (MVC)
==========================================
Endpoints principales:
  POST /api/chat           - Enviar mensaje a la Entidad
  POST /api/session/create - Crear nueva sesión
  GET  /api/sessions       - Listar sesiones
  GET  /api/state          - Estado cognitivo actual
  GET  /api/history        - Historial de conversación
  POST /api/reset          - Reiniciar memoria
"""

import json
import uuid
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import ENTITY_DATA_DIR, USERS_DIR, BASE_DIR
from core.cognitive_loop import CognitiveLoop

import os
# ============================================
# CONFIGURACIÓN INICIAL
# ============================================

USERS_DIR.mkdir(parents=True, exist_ok=True)

# Configuración de caché de HuggingFace (por si se usan embeddings u otros modelos)
os.environ["HF_HOME"] = str(BASE_DIR / "models" / "hf_cache")

# ============================================
# MODELOS DE DATOS (Pydantic)
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
        loop.flow_manager.start()
        sessions[session_id] = loop
        print(f"[Session] Sesión cargada: {session_id}")
    
    return sessions[session_id]


# ============================================
# INICIALIZACIÓN DEL SISTEMA
# ============================================

print("=" * 60)
print("🧠 Inicializando Sibelium Cognitive Assistant (MVC)...")
print("=" * 60)

print("📦 Precargando LLM...")
from core.llm import LLMModel
llm = LLMModel.get_instance()
llm.load_model()
print("   ✅ LLM cargado")

# Precargar sesión default
_default_loop = get_or_create_loop("default")
_default_loop.flow_manager.start()
print("   ✅ FlowManager arrancado")

print("=" * 60)
print("🚀 Servidor listo en http://127.0.0.1:8000")
print("=" * 60)


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
# ENDPOINTS DE SESIÓN
# ============================================

@app.post("/api/session/create")
async def create_session(request: SessionCreateRequest):
    session_id = uuid.uuid4().hex[:12]
    session_dir = USERS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    meta_path = session_dir / "meta.json"
    meta_path.write_text(json.dumps({
        "name": request.name,
        "created": datetime.now().isoformat(),
        "private": False
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    
    get_or_create_loop(session_id)
    return {"session_id": session_id, "name": request.name}

@app.get("/api/sessions")
async def list_sessions():
    result = []
    if USERS_DIR.exists():
        for session_dir in sorted(USERS_DIR.iterdir(), key=lambda d: d.name):
            if session_dir.is_dir():
                meta_path = session_dir / "meta.json"
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except: pass
                result.append({
                    "session_id": session_dir.name,
                    "name": meta.get("name", session_dir.name[:8]),
                    "created": meta.get("created", ""),
                    "private": meta.get("private", False)
                })
    return {"sessions": result}

# ============================================
# ENDPOINTS DE CONVERSACIÓN
# ============================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    log_line()
    print(f"[Chat] Mensaje recibido: {request.message[:100]}...")
    
    try:
        loop = get_or_create_loop(request.session_id)
        result = loop.process(request.message)
        
        if result is None or "response" not in result:
            raise HTTPException(status_code=500, detail="Respuesta inválida del sistema")
        
        response_text = result.get("response", "")
        print(f"[Chat] ✅ Respuesta generada ({len(response_text)} chars)")
        print(f"[Chat] 💬 {response_text[:200]}...")
            
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
    loop = get_or_create_loop(session_id)
    state = loop.get_last_state()
    return state if state else {"status": "empty"}

@app.get("/api/history")
async def get_history(session_id: str = "default"):
    loop = get_or_create_loop(session_id)
    return {
        "history": loop.get_history(),
        "thought_history": loop.get_last_thoughts(),
        "cognitive_state": loop.get_last_state(),
    }

@app.post("/api/reset")
async def reset_endpoint(session_id: str = "default"):
    print("[System] 🔄 Reiniciando memoria...")
    loop = get_or_create_loop(session_id)
    loop.reset()
    print("[System] ✅ Memoria reiniciada")
    return {"status": "reset"}

# ============================================
# UTILIDADES Y DEBUG
# ============================================

def log_line(char="=", length=60):
    print(char * length)

@app.get("/debug")
async def debug():
    return {
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
# STATIC FILES (FRONTEND)
# ============================================

frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")