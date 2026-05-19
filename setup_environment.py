import os
from pathlib import Path

MODELS_CACHE_DIR = Path(__file__).parent / "models_cache"
MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(MODELS_CACHE_DIR / "huggingface")
os.environ["TORCH_HOME"] = str(MODELS_CACHE_DIR / "torch")
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(MODELS_CACHE_DIR / "sentence_transformers")
os.environ["WHISPER_CACHE_DIR"] = str(MODELS_CACHE_DIR / "whisper")
os.environ["CHROMA_CACHE_PATH"] = str(MODELS_CACHE_DIR / "chroma")