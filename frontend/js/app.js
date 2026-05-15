console.log('🚀 Inicializando Sibelium Cognitive Assistant...');

document.addEventListener('DOMContentLoaded', () => {
  console.log('📄 DOM cargado, inicializando aplicación...');

  const messageInput = document.getElementById('message-input');
  const sendButton = document.getElementById('btn-send');
  const resetButton = document.getElementById('btn-reset');
  const btnToggleSessions = document.getElementById('btn-toggle-sessions');
  const sessionsSidebar = document.getElementById('sessions-sidebar');
  const sessionsList = document.getElementById('sessions-list');
  const voiceBtn = document.getElementById('btn-voice');
  const fileBtn = document.getElementById('btn-file');
  const fileInput = document.getElementById('file-input');
  const btnNewSession = document.getElementById('btn-new-session');
  const btnLockSession = document.getElementById('btn-lock-session');
  const lockModal = document.getElementById('lock-modal');
  const unlockModal = document.getElementById('unlock-modal');
  const btnReopenSidebar = document.getElementById('btn-reopen-sidebar');

  const ALLOWED_EXTENSIONS = [
    '.txt', '.md', '.pdf', '.json', '.csv',
    '.py', '.js', '.html', '.css',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
    '.mp3', '.wav', '.ogg', '.m4a', '.flac'
  ];
  const MAX_FILE_SIZE = 50 * 1024 * 1024;

  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  let pendingFile = null;
  let currentSessionId = localStorage.getItem('currentSessionId') || 'default';
  let currentEventSource = null;
  let sessionsData = [];

  if (!messageInput || !sendButton || !resetButton) {
    console.error('❌ Elementos del DOM no encontrados.');
    return;
  }

  // ============================================
  // SIDEBAR TOGGLE
  // ============================================
  btnToggleSessions.addEventListener('click', () => {
    sessionsSidebar.classList.toggle('collapsed');
    btnToggleSessions.textContent = sessionsSidebar.classList.contains('collapsed') ? '▶' : '◀';
  });
  btnReopenSidebar.addEventListener('click', () => {
    sessionsSidebar.classList.remove('collapsed');
    btnToggleSessions.textContent = '◀';
});

  // ============================================
  // GESTIÓN DE SESIONES
  // ============================================

async function loadSessions() {
    try {
      const res = await fetch('/api/sessions');
      const data = await res.json();
      sessionsData = data.sessions;
      renderSessionsList();
      // Ocultar mensaje de conexión
      const connecting = document.getElementById('connecting-message');
      if (connecting) connecting.remove();
    } catch (e) {
      console.error('Error cargando sesiones:', e);
    }
  }

  function renderSessionsList() {
    sessionsList.innerHTML = '';
    sessionsData.forEach(s => {
      const item = document.createElement('div');
      item.className = 'session-item';
      if (s.session_id === currentSessionId) item.classList.add('active');
      item.dataset.sessionId = s.session_id;

      const name = document.createElement('span');
      name.className = 'session-item-name';
      name.textContent = s.name;

      const lock = document.createElement('span');
      lock.className = 'session-item-lock';
      lock.textContent = s.private ? '🔒' : '';

      item.appendChild(name);
      item.appendChild(lock);

      item.addEventListener('click', () => {
        if (s.private && s.session_id !== 'default') {
          handleSessionLocked(s.session_id);
        } else {
          switchSession(s.session_id);
        }
      });

      sessionsList.appendChild(item);
    });
    updateLockButton();
  }

  async function switchSession(sessionId) {
    currentSessionId = sessionId;
    localStorage.setItem('currentSessionId', sessionId);
    renderSessionsList();
    clearChat();
    loadHistory();
    reconnectSSE();
  }

  async function createNewSession() {
    const name = prompt('Nombre de la nueva sesión:', 'Sesión ' + new Date().toLocaleDateString());
    if (!name) return;
    try {
      const res = await fetch('/api/session/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const data = await res.json();
      await loadSessions();
      switchSession(data.session_id);
    } catch (e) {
      console.error('Error creando sesión:', e);
    }
  }

  function updateLockButton() {
    const current = sessionsData.find(s => s.session_id === currentSessionId);
    if (current && current.private) {
      btnLockSession.textContent = '🔒';
      btnLockSession.title = 'Quitar protección';
    } else {
      btnLockSession.textContent = '🔓';
      btnLockSession.title = 'Proteger sesión';
    }
  }

  // ============================================
  // MODALES DE PROTECCIÓN
  // ============================================

  btnLockSession.addEventListener('click', () => {
    const current = sessionsData.find(s => s.session_id === currentSessionId);
    const isPrivate = current && current.private;
    document.getElementById('lock-password').value = '';
    document.getElementById('lock-password-confirm').value = '';
    document.getElementById('lock-error').style.display = 'none';
    document.getElementById('btn-lock-confirm').style.display = isPrivate ? 'none' : '';
    document.getElementById('btn-lock-remove').style.display = isPrivate ? '' : 'none';
    lockModal.style.display = 'flex';
  });

  document.getElementById('btn-lock-cancel').addEventListener('click', () => {
    lockModal.style.display = 'none';
  });

  document.getElementById('btn-lock-confirm').addEventListener('click', async () => {
    const pass = document.getElementById('lock-password').value;
    const confirm = document.getElementById('lock-password-confirm').value;
    if (!pass || pass.length < 3) {
      showLockError('La clave debe tener al menos 3 caracteres.');
      return;
    }
    if (pass !== confirm) {
      showLockError('Las claves no coinciden.');
      return;
    }
    try {
      await fetch('/api/session/lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, password: pass })
      });
      lockModal.style.display = 'none';
      loadSessions();
    } catch (e) {
      showLockError('Error al proteger la sesión.');
    }
  });

  document.getElementById('btn-lock-remove').addEventListener('click', async () => {
    try {
      await fetch('/api/session/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, password: '', remove: true })
      });
      lockModal.style.display = 'none';
      loadSessions();
    } catch (e) {
      showLockError('Error al quitar protección.');
    }
  });

  function showLockError(msg) {
    const err = document.getElementById('lock-error');
    err.textContent = msg;
    err.style.display = 'block';
  }

  document.getElementById('btn-unlock-confirm').addEventListener('click', async () => {
    const pass = document.getElementById('unlock-password').value;
    try {
      const res = await fetch('/api/session/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, password: pass, remove: false })
      });
      if (res.ok) {
        unlockModal.style.display = 'none';
        loadHistory();
        loadSessions();
      } else {
        document.getElementById('unlock-error').textContent = 'Clave incorrecta.';
        document.getElementById('unlock-error').style.display = 'block';
      }
    } catch (e) {
      document.getElementById('unlock-error').textContent = 'Error al desbloquear.';
      document.getElementById('unlock-error').style.display = 'block';
    }
  });

  document.getElementById('btn-unlock-cancel').addEventListener('click', () => {
    unlockModal.style.display = 'none';
    switchSession('default');
  });

  function handleSessionLocked(sessionId) {
    currentSessionId = sessionId;
    localStorage.setItem('currentSessionId', sessionId);
    document.getElementById('unlock-password').value = '';
    document.getElementById('unlock-error').style.display = 'none';
    unlockModal.style.display = 'flex';
  }

  btnNewSession.addEventListener('click', createNewSession);

  // ============================================
  // VOZ
  // ============================================
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunks = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
      mediaRecorder.onstop = async () => {
        await sendVoiceMessage(new Blob(audioChunks, { type: 'audio/webm' }));
        stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.start();
      isRecording = true;
      voiceBtn.textContent = '⏹';
      voiceBtn.classList.add('recording');
      appendMessage('user', '🎤 Grabando...');
    } catch (e) {
      appendMessage('assistant', 'No se pudo acceder al micrófono.');
    }
  }

  function stopRecording() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;
      voiceBtn.textContent = '🎤';
      voiceBtn.classList.remove('recording');
      updateLastUserMessage('🎤 Mensaje de voz enviado');
    }
  }

  async function sendVoiceMessage(audioBlob) {
    voiceBtn.disabled = true;
    const fd = new FormData();
    fd.append('file', audioBlob, 'voice_message.webm');
    fd.append('session_id', currentSessionId);
    try {
      const res = await fetch('/api/voice-message', { method: 'POST', body: fd });
      const data = await res.json();
      updateLastUserMessage(`🎤 "${data.transcription}"`);
      appendMessage('assistant', data.response);
    } catch (e) {
      appendMessage('assistant', 'Error al procesar el mensaje de voz.');
    } finally { voiceBtn.disabled = false; }
  }

  if (voiceBtn) {
    voiceBtn.addEventListener('click', async () => {
      if (isRecording) { stopRecording(); } else { await startRecording(); }
    });
  }

  // ============================================
  // ARCHIVOS
  // ============================================
  if (fileBtn && fileInput) {
    fileBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        appendMessage('assistant', `Tipo no soportado: ${ext}.`);
        fileInput.value = ''; return;
      }
      if (file.size > MAX_FILE_SIZE) {
        appendMessage('assistant', `Archivo demasiado grande. Max: ${MAX_FILE_SIZE/1024/1024}MB.`);
        fileInput.value = ''; return;
      }
      pendingFile = file;
      messageInput.placeholder = `Mensaje (se adjuntará: ${file.name})...`;
      fileBtn.style.borderColor = 'var(--blue)';
      appendMessage('user', `📎 ${file.name}. Escribe y envía.`);
    });
  }

  // ============================================
  // ENVÍO DE MENSAJE
  // ============================================
  async function sendMessage() {
    const text = messageInput.value.trim();
    const file = pendingFile;
    if (!text && !file) return;

    if (file) {
      appendMessage('user', `📎 ${file.name}${text ? '\n' + text : ''}`);
      messageInput.value = '';
      messageInput.placeholder = 'Escribe tu mensaje...';
      pendingFile = null;
      fileBtn.style.borderColor = '';
      disableInputs(true);
      const fd = new FormData();
      fd.append('file', file);
      fd.append('session_id', currentSessionId);
      try {
        const uploadRes = await fetch('/api/upload', { method: 'POST', body: fd });
        const uploadData = await uploadRes.json();
        const analysisText = uploadData.analysis?.interpretation || uploadData.analysis?.description || 'Archivo recibido.';
        const textMsg = `[Archivo subido: ${file.name}] ${text || ''}\n\nAnalisis: ${analysisText}`;
        const result = await window.api.chat(textMsg);
        appendMessage('assistant', result.response);
      } catch (e) {
        appendMessage('assistant', 'Error al procesar el archivo.');
      } finally { disableInputs(false); fileInput.value = ''; }
    } else {
      appendMessage('user', text);
      messageInput.value = '';
      disableInputs(true);
      appendMessage('assistant', 'Pensando...', true);
      window.api.chat(text)
        .then((result) => {
          updateAssistantMessage(result.response);
        })
        .catch(() => updateAssistantMessage('Error al generar la respuesta.'))
        .finally(() => { disableInputs(false); messageInput.focus(); });
    }
  }

  function disableInputs(disabled) {
    messageInput.disabled = disabled;
    sendButton.disabled = disabled;
    if (fileBtn) fileBtn.disabled = disabled;
    if (voiceBtn) voiceBtn.disabled = disabled;
  }

  function appendMessage(role, text, isThinking = false) {
    const container = document.getElementById('chat-messages');
    const msg = document.createElement('div');
    msg.className = `message message-${role}`;
    if (isThinking) msg.classList.add('thinking');
    const formatted = role === 'assistant' && !isThinking ? renderMarkdown(escapeHtml(text)) : escapeHtml(text);
    msg.innerHTML = `<div>${formatted}</div><div class="message-timestamp">${new Date().toLocaleTimeString()}</div>`;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
  }

  function renderMarkdown(text) {
    // Saltos de línea
    text = text.replace(/\n/g, '<br>');
    // Negrita
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Itálica
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Código inline
    text = text.replace(/`(.*?)`/g, '<code>$1</code>');
    return text;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function updateAssistantMessage(text) {
    const thinking = document.querySelector('.message-assistant.thinking');
    if (thinking) {
      thinking.classList.remove('thinking');
      thinking.innerHTML = `<div>${escapeHtml(text)}</div><div class="message-timestamp">${new Date().toLocaleTimeString()}</div>`;
      return;
    }
    appendMessage('assistant', text);
  }

  function updateLastUserMessage(text) {
    const msgs = document.querySelectorAll('.message-user');
    const last = msgs[msgs.length - 1];
    if (last) last.innerHTML = `<div>${escapeHtml(text)}</div><div class="message-timestamp">${new Date().toLocaleTimeString()}</div>`;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function clearChat() {
    document.getElementById('chat-messages').innerHTML = '';
  }

  function resetSession() {
    window.api.reset().then(() => {
      clearChat();
      appendMessage('assistant', 'Memoria reiniciada.');
    }).catch(() => appendMessage('assistant', 'Error al reiniciar.'));
  }

  function loadHistory() {
    window.api.getHistory().then((data) => {
      if (Array.isArray(data.history)) {
        document.getElementById('chat-messages').innerHTML = '';
        data.history.forEach(item => appendMessage(item.role, item.text));
      }
    }).catch(() => {});
  }

  function reconnectSSE() {
    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource('/api/nexus/proactive-stream?session_id=' + currentSessionId);
    currentEventSource.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      appendMessage('assistant', '💬 ' + msg.message);
    };
  }

  sendButton.addEventListener('click', sendMessage);
  messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  resetButton.addEventListener('click', resetSession);

  const heartbeat = setInterval(() => fetch('/api/heartbeat', { method: 'POST' }).catch(() => {}), 30000);
  window.addEventListener('beforeunload', () => {
    clearInterval(heartbeat);
    navigator.sendBeacon('/api/heartbeat', JSON.stringify({ closing: true }));
  });

  // Inicialización
  loadSessions().then(() => {
    loadHistory();
    reconnectSSE();
  });

  console.log('✅ Aplicación inicializada correctamente');
});