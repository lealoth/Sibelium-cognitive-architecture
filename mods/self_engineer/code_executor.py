"""Ejecutor de código en sandbox con feedback cerebeloso."""
import subprocess
import tempfile
import traceback
from pathlib import Path


class CodeExecutor:
    """Sandbox con feedback estructurado (Cerebelo Computacional)."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def execute(self, code: str, expected_output: str = "") -> dict:
        """Ejecuta código y devuelve feedback cerebeloso estructurado."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name

        result = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "cerebellar_feedback": {}
        }

        try:
            exec_result = subprocess.run(
                ['python', temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            result["stdout"] = exec_result.stdout[:500]
            result["stderr"] = exec_result.stderr[:500]
            result["exit_code"] = exec_result.returncode
            result["success"] = exec_result.returncode == 0

            if not result["success"]:
                result["cerebellar_feedback"] = self._analyze_failure(
                    code, exec_result.stderr, expected_output
                )
            elif expected_output:
                result["cerebellar_feedback"] = self._analyze_output_match(
                    exec_result.stdout, expected_output
                )

        except subprocess.TimeoutExpired:
            result["stderr"] = f"Timeout: ejecución excedió {self.timeout}s"
            result["cerebellar_feedback"] = {
                "error_type": "TimeoutExpired",
                "linea_exacta": None,
                "codigo_causante": "Timeout en el bloque completo",
                "error_prediction_gap": "El código no terminó en el tiempo esperado",
                "sugerencia_sinaptica": "Verificar bucles infinitos o reducir complejidad"
            }
        except Exception as e:
            result["stderr"] = str(e)
            result["cerebellar_feedback"] = {
                "error_type": type(e).__name__,
                "linea_exacta": None,
                "codigo_causante": str(e)[:200],
                "error_prediction_gap": "Error inesperado del sistema",
                "sugerencia_sinaptica": "Revisar la sintaxis y dependencias del código"
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)

        return result

    def _analyze_failure(self, code: str, stderr: str, expected: str) -> dict:
        """Analiza un fallo de ejecución con precisión cerebelosa."""
        lines = code.split('\n')

        # Extraer número de línea del error
        line_number = None
        culprit_line = ""

        import re
        line_match = re.search(r'line (\d+)', stderr)
        if line_match:
            line_number = int(line_match.group(1))
            if line_number <= len(lines):
                culprit_line = lines[line_number - 1].strip()

        # Extraer tipo de error
        error_type = "Unknown"
        error_match = re.search(r'(\w+Error):', stderr)
        if error_match:
            error_type = error_match.group(1)
        elif "Timeout" in stderr:
            error_type = "TimeoutExpired"
        elif "SyntaxError" in stderr:
            error_type = "SyntaxError"

        # Calcular gap de predicción
        gap = "No se proporcionó output esperado para comparar"
        if expected:
            gap = f"Esperado: {expected[:100]}\nObtenido: {stderr[:100]}"

        # Generar sugerencia sináptica basada en el tipo de error
        suggestions = {
            "SyntaxError": "Verificar sintaxis en la línea indicada. Posible falta de ':' o paréntesis.",
            "IndentationError": "Corregir indentación en la línea indicada.",
            "NameError": "Verificar que la variable o función esté definida antes de usarse.",
            "TypeError": "Verificar tipos de datos. Posible confusión entre str/int/list.",
            "ValueError": "Verificar que el valor pasado sea válido para la operación.",
            "IndexError": "Verificar índices de lista. Posible acceso fuera de rango.",
            "KeyError": "Verificar que la clave exista en el diccionario.",
            "AttributeError": "Verificar que el objeto tenga el atributo o método llamado.",
            "ModuleNotFoundError": "Verificar que el módulo esté instalado o el nombre correcto.",
            "ImportError": "Verificar que el módulo o función exista en la librería.",
            "ZeroDivisionError": "Verificar división por cero. Añadir validación de denominador.",
            "FileNotFoundError": "Verificar que la ruta del archivo sea correcta.",
            "TimeoutExpired": "El código es demasiado lento. Optimizar bucles o reducir complejidad.",
        }
        suggestion = suggestions.get(error_type, "Revisar la línea indicada y corregir el error.")

        return {
            "error_type": error_type,
            "linea_exacta": line_number,
            "codigo_causante": culprit_line[:200],
            "error_prediction_gap": gap,
            "sugerencia_sinaptica": suggestion
        }

    def _analyze_output_match(self, stdout: str, expected: str) -> dict:
        """Compara el output real con el esperado."""
        stdout_clean = stdout.strip()
        expected_clean = expected.strip()
        match = stdout_clean == expected_clean

        return {
            "error_type": "OutputMismatch" if not match else "Success",
            "linea_exacta": None,
            "codigo_causante": "",
            "error_prediction_gap": f"Esperado: {expected_clean[:100]}\nObtenido: {stdout_clean[:100]}",
            "sugerencia_sinaptica": "Ajustar la lógica para que coincida con el output esperado" if not match else "Output coincide con lo esperado"
        }

    def test_solution(self, solution_code: str, test_code: str, expected_output: str = "") -> dict:
        """Ejecuta una solución con tests y feedback cerebeloso."""
        full_code = f"{solution_code}\n\n{test_code}"
        return self.execute(full_code, expected_output)