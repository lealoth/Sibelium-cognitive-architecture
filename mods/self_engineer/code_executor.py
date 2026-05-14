"""Ejecutor de código en sandbox."""
import subprocess
import tempfile
from pathlib import Path


class CodeExecutor:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    def execute(self, code: str) -> dict:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ['python', temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:500],
                "stderr": result.stderr[:500],
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Timeout: ejecución excedió {self.timeout}s",
                "exit_code": -1
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def test_solution(self, problem_description: str, solution_code: str, test_code: str) -> dict:
        full_code = f"{solution_code}\n\n{test_code}"
        return self.execute(full_code)