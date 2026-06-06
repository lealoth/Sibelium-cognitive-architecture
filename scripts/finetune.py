"""
Fine-tuning incremental para entidades de Sibelium.
Usa llama.cpp con LoRA para ajustar el modelo base con las interacciones registradas.
"""
import json
import subprocess
import sys
from pathlib import Path

def finetune(entity_name: str, base_model: str, data_path: str, output_path: str):
    """Ejecuta fine-tuning LoRA con los datos acumulados."""
    
    # Verificar que hay suficientes datos
    data_file = Path(data_path)
    if not data_file.exists():
        print(f"No hay datos de entrenamiento para {entity_name}.")
        return
    
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if len(lines) < 10:
        print(f"Solo {len(lines)} registros. Se necesitan al menos 10 para fine-tuning.")
        return
    
    print(f"Fine-tuning {entity_name} con {len(lines)} registros...")
    
    # Convertir JSONL a formato llama.cpp (prompt-completion)
    formatted_data = []
    for line in lines:
        record = json.loads(line)
        formatted_data.append({
            "prompt": record["prompt"],
            "completion": record["response"]
        })
    
    # Guardar en formato temporal
    temp_file = data_file.parent / "temp_training.json"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(formatted_data, f, ensure_ascii=False, indent=2)
    
    # Ejecutar fine-tuning con llama.cpp
    cmd = [
        "python", "-m", "llama_cpp.finetune",
        "--model", base_model,
        "--data", str(temp_file),
        "--output", output_path,
        "--epochs", "3",
        "--batch-size", "2",
        "--lora-rank", "8"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Fine-tuning completado. Modelo guardado en {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error en fine-tuning: {e}")
    except FileNotFoundError:
        print("llama.cpp no está instalado o no tiene soporte para fine-tuning.")
        print("Guardando datos para fine-tuning externo...")
    
    # Limpiar archivo temporal
    temp_file.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python finetune.py <entity_name> <base_model_path> <data_path> <output_path>")
        sys.exit(1)
    
    finetune(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])