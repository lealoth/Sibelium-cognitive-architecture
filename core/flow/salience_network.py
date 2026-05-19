"""
Sistema #36: Red de Saliencia (Salience Network)
Homólogo a la Ínsula Anterior y Córtex Cingulado Anterior.

Actúa como interruptor entre:
- DMN (Default Mode Network): _fast_tick y _slow_tick (procesamiento interno)
- CEN (Central Executive Network): Respuesta al usuario (atención externa)

Cuando entra un estímulo externo (mensaje del usuario), la Red de Saliencia:
1. Inhibe la DMN (pausa ticks de fondo)
2. Activa la CEN (prioriza respuesta)
3. Al terminar la respuesta, reactiva la DMN
"""

import threading
import time


class SalienceNetwork:
    """Interruptor atencional entre redes cognitivas."""
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        if SalienceNetwork._instance is not None:
            return
        SalienceNetwork._instance = self

        self.network_state = "DEFAULT_MODE"  # DMN activa por defecto
        self._state_lock = threading.Lock()
        self._dmn_paused_since = None

    @property
    def is_dmn_active(self) -> bool:
        with self._state_lock:
            return self.network_state == "DEFAULT_MODE"

    @property
    def is_cen_active(self) -> bool:
        with self._state_lock:
            return self.network_state == "CENTRAL_EXECUTIVE"

    def on_user_message(self):
        """
        Activa la Red de Saliencia ante estímulo externo.
        Inhibe la DMN, activa la CEN.
        """
        with self._state_lock:
            if self.network_state == "CENTRAL_EXECUTIVE":
                return  # Ya está en modo atención
            self.network_state = "CENTRAL_EXECUTIVE"
            self._dmn_paused_since = time.time()
        print("   [SN] Estímulo externo detectado. Inhibiendo DMN (ticks de fondo)...")

    def on_response_sent(self):
        """
        Desactiva la Red de Saliencia.
        Reactiva la DMN para procesamiento interno.
        """
        with self._state_lock:
            if self.network_state == "DEFAULT_MODE":
                return
            self.network_state = "DEFAULT_MODE"
            paused_duration = time.time() - (self._dmn_paused_since or time.time())
        print(f"   [SN] Respuesta enviada. Reactivando DMN (pausada por {paused_duration:.1f}s).")

    def get_state(self) -> str:
        with self._state_lock:
            return self.network_state