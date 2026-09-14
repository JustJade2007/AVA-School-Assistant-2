"""Embedded web user interface for Jade's AI Humanizer daemon."""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jade's AI Humanizer</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✨</text></svg>">
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --accent: #238636;
      --accent-hover: #2ea043;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --text-bright: #f0f6fc;
      --tag-bg: #21262d;
      --focus-ring: #58a6ff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px 16px;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      width: 100%;
      flex: 1;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
      gap: 12px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo-badge {
      background: linear-gradient(135deg, #238636, #1f6feb);
      color: #fff;
      font-size: 20px;
      font-weight: bold;
      width: 40px;
      height: 40px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    h1 {
      font-size: 22px;
      font-weight: 600;
      color: var(--text-bright);
    }
    .subtitle {
      font-size: 13px;
      color: var(--text-muted);
    }
    .header-links {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .header-links a {
      color: var(--focus-ring);
      text-decoration: none;
      font-size: 13px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: var(--tag-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      transition: all 0.2s;
    }
    .header-links a:hover {
      background: var(--border);
    }

    /* Key Config Bar */
    .key-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 16px;
      margin-bottom: 24px;
      gap: 14px;
      flex-wrap: wrap;
    }
    .key-bar-left {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 1;
      min-width: 320px;
    }
    .key-label {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-bright);
      white-space: nowrap;
    }
    .key-input-wrapper {
      display: flex;
      align-items: center;
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 2px 6px;
    }
    .key-input-wrapper input {
      background: transparent;
      border: none;
      color: var(--text-bright);
      font-family: monospace;
      font-size: 13px;
      flex: 1;
      padding: 6px;
      outline: none;
    }
    .btn-icon {
      background: transparent;
      border: none;
      cursor: pointer;
      color: var(--text-muted);
      padding: 4px 6px;
      font-size: 14px;
    }
    .btn-icon:hover {
      color: var(--text-bright);
    }
    .btn-sm {
      background: var(--tag-bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.2s;
      white-space: nowrap;
    }
    .btn-sm:hover {
      background: var(--border);
      color: var(--text-bright);
    }
    .key-bar-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.2px;
    }
    .badge-offline {
      background: rgba(240, 136, 62, 0.15);
      color: #f0883e;
      border: 1px solid rgba(240, 136, 62, 0.4);
    }
    .badge-online {
      background: rgba(46, 160, 67, 0.15);
      color: #3fb950;
      border: 1px solid rgba(46, 160, 67, 0.4);
    }

    .main-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      margin-bottom: 24px;
    }
    @media (max-width: 860px) {
      .main-grid { grid-template-columns: 1fr; }
    }
    .panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .panel-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--text-bright);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    textarea {
      width: 100%;
      height: 330px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-bright);
      font-family: inherit;
      font-size: 14px;
      padding: 14px;
      resize: vertical;
      line-height: 1.6;
    }
    textarea:focus {
      outline: none;
      border-color: var(--focus-ring);
      box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2);
    }
    .controls-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 14px;
      margin-bottom: 16px;
    }
    .control-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .control-group label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    select {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text-bright);
      padding: 8px 10px;
      font-size: 13px;
      outline: none;
    }
    select:focus {
      border-color: var(--focus-ring);
    }
    .btn-primary {
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 12px 20px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: background 0.2s;
    }
    .btn-primary:hover {
      background: var(--accent-hover);
    }
    .btn-primary:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .btn-copy {
      background: var(--tag-bg);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-copy:hover {
      background: var(--border);
      color: var(--text-bright);
    }
    .metrics-bar {
      display: flex;
      gap: 12px;
      margin-top: 14px;
      padding: 10px 14px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      flex-wrap: wrap;
      align-items: center;
      font-size: 13px;
    }
    .metric {
      color: var(--text-muted);
    }
    .metric strong {
      color: var(--text-bright);
    }
    .metric-engine {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .tags-container {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }
    .tag {
      background: rgba(218, 54, 51, 0.15);
      border: 1px solid rgba(218, 54, 51, 0.3);
      color: #f85149;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 12px;
      text-decoration: line-through;
    }
    .offline-notice {
      background: rgba(240, 136, 62, 0.1);
      border: 1px solid rgba(240, 136, 62, 0.3);
      border-radius: 8px;
      padding: 10px 14px;
      color: #f0883e;
      font-size: 13px;
      margin-top: 12px;
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }
    footer {
      text-align: center;
      font-size: 12px;
      color: var(--text-muted);
      margin-top: auto;
      padding-top: 20px;
    }
    .spinner {
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255,255,255,0.3);
      border-radius: 50%;
      border-top-color: #fff;
      animation: spin 0.8s linear infinite;
      margin-right: 8px;
      vertical-align: middle;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="logo-badge">JH</div>
        <div>
          <h1>Jade's AI Humanizer</h1>
          <div class="subtitle">100% Local & Zero-Backend Text Humanization Engine</div>
        </div>
      </div>
      <div class="header-links">
        <a href="/docs" target="_blank">📚 Swagger API Docs</a>
        <a href="/health" target="_blank">🩺 Health Status</a>
      </div>
    </header>

    <!-- API Key & Engine Config Bar -->
    <div class="key-bar">
      <div class="key-bar-left">
        <span class="key-label">🔑 Gemini API Key:</span>
        <div class="key-input-wrapper">
          <input id="apiKeyInput" type="password" placeholder="Paste Gemini API Key here (or leave empty for offline mode)" autocomplete="off">
          <button id="toggleKeyBtn" class="btn-icon" title="Show/Hide Key" onclick="toggleKeyVisibility()">👁️</button>
        </div>
        <button id="saveKeyBtn" class="btn-sm" onclick="saveApiKey()">Save Key</button>
        <button id="clearKeyBtn" class="btn-sm" onclick="clearApiKey()">Clear</button>
      </div>
      <div class="key-bar-right">
        <span id="engineBadge" class="badge badge-offline">🟠 Detecting Engine...</span>
      </div>
    </div>

    <div class="main-grid">
      <!-- Input Panel -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">📝 AI-Generated Text</div>
          <span id="charCount" style="font-size: 12px; color: var(--text-muted);">0 words</span>
        </div>
        <textarea id="inputText" placeholder="Paste your AI-generated text here..."></textarea>
        
        <div class="controls-grid">
          <div class="control-group">
            <label for="modeSelect">Mode</label>
            <select id="modeSelect">
              <option value="deep" selected>Deep (Anti-Detection)</option>
              <option value="budget">Budget (Fast / Low Token)</option>
            </select>
          </div>
          <div class="control-group">
            <label for="toneSelect">Tone</label>
            <select id="toneSelect">
              <option value="casual">Casual (Natural)</option>
              <option value="neutral" selected>Neutral (Balanced)</option>
              <option value="professional">Professional</option>
              <option value="academic">Academic</option>
            </select>
          </div>
          <div class="control-group">
            <label for="levelSelect">Reading Level</label>
            <select id="levelSelect">
              <option value="general" selected>General</option>
              <option value="high_school">High School</option>
              <option value="middle_school">Middle School</option>
              <option value="college">College</option>
            </select>
          </div>
        </div>

        <button id="humanizeBtn" class="btn-primary" onclick="handleHumanize()">
          ✨ Humanize Text
        </button>
      </div>

      <!-- Output Panel -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">🌿 Natural Human Text</div>
          <button id="copyBtn" class="btn-copy" onclick="copyOutput()" style="display:none;">📋 Copy</button>
        </div>
        <textarea id="outputText" readonly placeholder="Humanized text will appear here..."></textarea>
        
        <div id="metricsBar" class="metrics-bar" style="display: none;">
          <div class="metric">Engine: <strong id="mEngine">--</strong></div>
          <div class="metric">Tokens Billed: <strong id="mTokens">--</strong></div>
          <div class="metric">Flesch Ease: <strong id="mFlesch">--</strong></div>
          <div class="metric">Mode: <strong id="mMode">--</strong></div>
        </div>

        <div id="offlineNotice" class="offline-notice" style="display: none;">
          <div>ℹ️</div>
          <div>
            <strong>Running in Offline Mode:</strong> Text was processed 100% locally on your computer with rule-based de-flating and guardrails. <strong>0 API tokens were charged.</strong> To use Gemini 2.5 Flash Lite, paste your API key in the top bar.
          </div>
        </div>

        <div id="tagsSection" style="display:none; margin-top:12px;">
          <div style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">De-Flated Phrases & Clichés Replaced:</div>
          <div id="tagsList" class="tags-container"></div>
        </div>
      </div>
    </div>

    <footer>
      Jade's AI Humanizer v1.2.0 • Powered by local client-side heuristics & Gemini Flash Lite • Runs 100% on your machine.
    </footer>
  </div>

  <script>
    const apiKeyInput = document.getElementById('apiKeyInput');
    const engineBadge = document.getElementById('engineBadge');
    const inputText = document.getElementById('inputText');
    const outputText = document.getElementById('outputText');
    const charCount = document.getElementById('charCount');
    const humanizeBtn = document.getElementById('humanizeBtn');
    const copyBtn = document.getElementById('copyBtn');
    const metricsBar = document.getElementById('metricsBar');
    const mEngine = document.getElementById('mEngine');
    const mTokens = document.getElementById('mTokens');
    const mFlesch = document.getElementById('mFlesch');
    const mMode = document.getElementById('mMode');
    const offlineNotice = document.getElementById('offlineNotice');
    const tagsSection = document.getElementById('tagsSection');
    const tagsList = document.getElementById('tagsList');

    // Load saved API key on startup
    const savedKey = localStorage.getItem('gemini_api_key') || '';
    if (savedKey) {
      apiKeyInput.value = savedKey;
    }

    // Refresh health and engine badge
    async function updateEngineStatus() {
      const currentKey = apiKeyInput.value.trim();
      try {
        const url = currentKey ? `/health?api_key=${encodeURIComponent(currentKey)}` : '/health';
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data.api_key_configured) {
            engineBadge.className = 'badge badge-online';
            engineBadge.innerText = '🟢 Online (Gemini 3.5 Flash Lite)';
          } else {
            engineBadge.className = 'badge badge-offline';
            engineBadge.innerText = '🟠 Offline (No API Key)';
          }
        }
      } catch (e) {
        engineBadge.className = 'badge badge-offline';
        engineBadge.innerText = '🟠 Offline Mode';
      }
    }

    // Initial check
    updateEngineStatus();

    function toggleKeyVisibility() {
      apiKeyInput.type = apiKeyInput.type === 'password' ? 'text' : 'password';
    }

    function saveApiKey() {
      const key = apiKeyInput.value.trim();
      if (key) {
        localStorage.setItem('gemini_api_key', key);
        alert('API Key saved in browser storage!');
      } else {
        localStorage.removeItem('gemini_api_key');
      }
      updateEngineStatus();
    }

    function clearApiKey() {
      apiKeyInput.value = '';
      localStorage.removeItem('gemini_api_key');
      updateEngineStatus();
    }

    apiKeyInput.addEventListener('input', () => {
      updateEngineStatus();
    });

    inputText.addEventListener('input', () => {
      const words = inputText.value.trim().split(/\\s+/).filter(Boolean).length;
      charCount.innerText = `${words} words`;
    });

    async function handleHumanize() {
      const text = inputText.value.trim();
      if (!text) {
        alert('Please enter or paste some text first.');
        return;
      }

      const activeKey = apiKeyInput.value.trim() || undefined;

      humanizeBtn.disabled = true;
      humanizeBtn.innerHTML = '<span class="spinner"></span> Humanizing...';
      outputText.value = '';
      offlineNotice.style.display = 'none';

      try {
        const response = await fetch('/v1/humanize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            mode: document.getElementById('modeSelect').value,
            tone: document.getElementById('toneSelect').value,
            reading_level: document.getElementById('levelSelect').value,
            preserve_markdown: true,
            api_key: activeKey
          })
        });

        if (!response.ok) {
          let errorMsg = `Humanization failed (HTTP ${response.status})`;
          try {
            const errData = await response.json();
            if (errData && errData.detail) {
              errorMsg = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail);
            }
          } catch (_) {
            try {
              const rawText = await response.text();
              if (rawText && rawText.trim()) {
                errorMsg = rawText.trim();
              }
            } catch (__) {}
          }
          throw new Error(errorMsg);
        }

        const data = await response.json();
        outputText.value = data.humanized_text;
        copyBtn.style.display = 'inline-block';

        // Update metrics
        metricsBar.style.display = 'flex';
        mFlesch.innerText = data.flesch_reading_ease.toFixed(1);
        mMode.innerText = data.mode;

        if (data.is_offline) {
          mEngine.innerHTML = '<span style="color:#f0883e;">🟠 Offline (Rule-Based)</span>';
          mTokens.innerHTML = '<strong>0</strong> <span style="color:var(--text-muted);font-size:11px;">(Offline - 100% Free)</span>';
          offlineNotice.style.display = 'flex';
        } else {
          mEngine.innerHTML = '<span style="color:#3fb950;">🟢 Gemini 3.5 Flash Lite</span>';
          mTokens.innerHTML = `<strong>${data.api_tokens_used || data.total_tokens}</strong> <span style="color:var(--text-muted);font-size:11px;">(P: ${data.prompt_tokens}, C: ${data.completion_tokens})</span>`;
          offlineNotice.style.display = 'none';
        }

        // Tags
        if (data.buzzwords_replaced && data.buzzwords_replaced.length > 0) {
          tagsSection.style.display = 'block';
          tagsList.innerHTML = data.buzzwords_replaced.map(w => `<span class="tag">${w}</span>`).join('');
        } else {
          tagsSection.style.display = 'none';
        }

      } catch (err) {
        outputText.value = 'Error: ' + err.message;
      } finally {
        humanizeBtn.disabled = false;
        humanizeBtn.innerHTML = '✨ Humanize Text';
      }
    }

    function copyOutput() {
      if (!outputText.value) return;
      navigator.clipboard.writeText(outputText.value).then(() => {
        const originalText = copyBtn.innerText;
        copyBtn.innerText = '✅ Copied!';
        setTimeout(() => copyBtn.innerText = originalText, 2000);
      });
    }
  </script>
</body>
</html>
"""
