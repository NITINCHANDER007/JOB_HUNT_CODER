/**
 * AutoApply AI — Floating AI Chatbot Component & In-Page Verification Center
 *
 * Core capabilities:
 * 1. Global bottom-right floating co-pilot across Dashboard, Apply, Profile, Settings.
 * 2. Embedded in-page application view modal for CAPTCHA, login, and registration.
 * 3. In-chat missing question Q&A with Yes/No, dropdowns, and text/number inputs.
 * 4. In-chat OTP/verification code entry with auto-resumption.
 * 5. Real-time step progress streaming and error reporting with 1-click retry.
 * 6. Explains security limitations (e.g. X-Frame-Options: SAMEORIGIN) and provides secure alternatives.
 */

const AIChatbot = (() => {
  let _isOpen = false;
  let _pollTimer = null;
  let _lastAppStatus = null;
  let _lastActionType = null;
  let _currentAppId = null;
  let _renderedLogIds = new Set();
  let _activeMissingFields = [];

  function init() {
    if (document.getElementById('ai-chatbot-root')) return;

    // 1. Mount Chatbot Root
    const root = document.createElement('div');
    root.id = 'ai-chatbot-root';
    root.className = 'ai-chatbot-root';

    root.innerHTML = `
      <!-- Floating Circular Button -->
      <button id="chatbot-toggle-btn" class="chatbot-toggle-btn" aria-label="Open AI Assistant" title="AutoApply AI Assistant">
        <span class="chatbot-ai-spark">✨</span>
        <span class="chatbot-close-icon">✕</span>
        <span id="chatbot-badge" class="chatbot-badge" style="display: none;">1</span>
      </button>

      <!-- Floating Chat Window -->
      <div id="chatbot-window" class="chatbot-window" style="display: none;">
        <!-- Header -->
        <div class="chatbot-header">
          <div class="chatbot-header-left">
            <div class="chatbot-avatar">🤖</div>
            <div>
              <div class="chatbot-title">AutoApply Co-Pilot</div>
              <div class="chatbot-subtitle" id="chatbot-subtitle">
                <span id="chatbot-status-dot" class="chatbot-status-dot"></span>
                <span id="chatbot-status-text">Online • Ready</span>
              </div>
            </div>
          </div>
          <div class="chatbot-header-actions">
            <button id="chatbot-minimize-btn" class="chatbot-btn-ghost" title="Minimize">−</button>
          </div>
        </div>

        <!-- Application Status Banner -->
        <div id="chatbot-app-banner" class="chatbot-app-banner" style="display: none;">
          <div id="chatbot-banner-text" style="font-weight: 500;"></div>
          <div id="chatbot-banner-badge"></div>
        </div>

        <!-- Messages Container -->
        <div id="chatbot-messages" class="chatbot-messages">
          <!-- Welcome message -->
          <div class="chat-msg bot">
            <div>👋 Hi there! I'm your <strong>AutoApply Co-Pilot</strong>.</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 6px;">
              I run and monitor your applications in the background. If an employer requires missing information, CAPTCHA, or sign-in, I'll assist you right here so you never need to leave!
            </div>
          </div>
        </div>

        <!-- Input Form -->
        <form id="chatbot-input-form" class="chatbot-input-form">
          <input
            type="text"
            id="chatbot-input-field"
            class="chatbot-input"
            placeholder="Ask anything or paste a job link..."
            autocomplete="off"
          />
          <button type="submit" class="chatbot-send-btn" id="chatbot-send-btn" title="Send">
            ➤
          </button>
        </form>
      </div>
    `;

    document.body.appendChild(root);

    // 2. Mount In-Page Embedded Portal Modal
    mountInPagePortalModal();

    // Event listeners
    document.getElementById('chatbot-toggle-btn').addEventListener('click', toggleChat);
    document.getElementById('chatbot-minimize-btn').addEventListener('click', closeChat);
    document.getElementById('chatbot-input-form').addEventListener('submit', handleUserInput);

    // Visibility & polling
    updateVisibility();
    window.addEventListener('hashchange', updateVisibility);
    startPolling();
  }

  // ---------------------------------------------------------------------------
  // In-Page Embedded Application Verification Modal
  // ---------------------------------------------------------------------------
  function mountInPagePortalModal() {
    if (document.getElementById('inpage-portal-modal-wrapper')) return;

    const wrapper = document.createElement('div');
    wrapper.id = 'inpage-portal-modal-wrapper';
    wrapper.innerHTML = `
      <div id="inpage-portal-overlay" class="inpage-portal-overlay" style="display: none;">
        <div id="inpage-portal-modal" class="inpage-portal-modal">
          <!-- Header -->
          <div class="inpage-portal-header">
            <div class="inpage-portal-title">
              <span>🛡️</span>
              <span id="inpage-portal-title-text">Secure In-Page Verification</span>
              <span class="status-badge badge-warning" style="font-size: 0.72rem; margin-left: 6px;">Live Session</span>
            </div>
            <div class="inpage-portal-controls">
              <button id="inpage-portal-expand-btn" class="chatbot-btn-ghost" title="Toggle Fullscreen">⛶</button>
              <button id="inpage-portal-reload-btn" class="chatbot-btn-ghost" title="Reload Frame">🔄</button>
              <button id="inpage-portal-close-btn" class="chatbot-btn-ghost" title="Close">✕</button>
            </div>
          </div>

          <!-- Body -->
          <div id="inpage-portal-body" class="inpage-portal-body">
            <div id="inpage-portal-loading" style="margin: auto; text-align: center; color: var(--text-primary); padding: 40px;">
              <div class="spinner-sm" style="width: 24px; height: 24px; margin: 0 auto 12px;"></div>
              <div>Checking employer portal security and loading frame…</div>
            </div>
          </div>

          <!-- Footer -->
          <div class="inpage-portal-footer">
            <div style="font-size: 0.8rem; color: var(--text-secondary);">
              🔒 Keep this page open while completing verification.
            </div>
            <button id="inpage-portal-resume-btn" class="btn btn-success btn-sm" style="padding: 8px 16px; font-weight: 600;">
              ▶️ I've Completed It — Resume Automation
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(wrapper);

    // Modal controls
    document.getElementById('inpage-portal-close-btn').addEventListener('click', closeInPagePortal);
    document.getElementById('inpage-portal-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('inpage-portal-overlay')) closeInPagePortal();
    });
    document.getElementById('inpage-portal-expand-btn').addEventListener('click', () => {
      document.getElementById('inpage-portal-modal').classList.toggle('expanded');
    });
  }

  async function openInPagePortal(appId, company, targetUrl, actionType) {
    const overlay = document.getElementById('inpage-portal-overlay');
    const titleText = document.getElementById('inpage-portal-title-text');
    const body = document.getElementById('inpage-portal-body');
    const resumeBtn = document.getElementById('inpage-portal-resume-btn');
    const reloadBtn = document.getElementById('inpage-portal-reload-btn');

    if (!overlay || !body) return;

    const actionLabel = actionType === 'captcha' ? 'CAPTCHA Challenge' : (actionType === 'login' ? 'Candidate Sign-In' : 'Verification');
    titleText.textContent = `${company || 'Employer'} — ${actionLabel}`;
    overlay.style.display = 'flex';

    // Show loading
    body.innerHTML = `
      <div style="margin: auto; text-align: center; color: var(--text-primary); padding: 40px;">
        <div class="spinner-sm" style="width: 24px; height: 24px; margin: 0 auto 12px;"></div>
        <div>Verifying employer portal compatibility…</div>
      </div>
    `;

    // Bind reload
    reloadBtn.onclick = () => openInPagePortal(appId, company, targetUrl, actionType);

    // Bind resume
    resumeBtn.onclick = async () => {
      resumeBtn.disabled = true;
      resumeBtn.innerHTML = '<span class="spinner-sm"></span> Resuming…';
      try {
        await chatAPI.resume(appId);
        closeInPagePortal();
        openChat();
        appendBotMessage(`🚀 Resuming automation for <strong>${escapeHtml(company || 'the job')}</strong>! I'm monitoring the process...`);
        startPolling();
      } catch (err) {
        showToast(err.message || 'Could not resume', 'error');
      } finally {
        resumeBtn.disabled = false;
        resumeBtn.textContent = "▶️ I've Completed It — Resume Automation";
      }
    };

    // Check embeddability
    try {
      const checkRes = await chatAPI.checkEmbeddable(targetUrl);
      if (checkRes && checkRes.embeddable) {
        // Can be embedded directly!
        body.innerHTML = `
          <iframe
            id="inpage-active-frame"
            class="inpage-portal-frame"
            src="${targetUrl}"
            sandbox="allow-forms allow-scripts allow-same-origin allow-popups allow-modals"
            title="Embedded Portal View"
          ></iframe>
        `;
      } else {
        // Portal restricts framing (e.g. X-Frame-Options: SAMEORIGIN / DENY)
        const reasonText = checkRes?.x_frame_options
          ? `X-Frame-Options: ${checkRes.x_frame_options.toUpperCase()}`
          : (checkRes?.reason || 'Browser Cross-Origin Security');

        body.innerHTML = `
          <div class="inpage-security-box">
            <div style="font-size: 34px;">🛡️</div>
            <div style="font-size: 1.05rem; font-weight: 600; color: var(--text-primary);">
              Employer Security Policy Detected
            </div>
            <div style="font-size: 0.84rem; color: var(--text-secondary); line-height: 1.55;">
              <strong>${escapeHtml(company || 'This employer')}</strong> enforces strict browser protection (<code>${escapeHtml(reasonText)}</code>) that prevents external framing directly inside other web pages.
            </div>
            <div style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 8px; padding: 14px; font-size: 0.82rem; text-align: left; color: var(--text-primary); line-height: 1.45;">
              <strong>💡 Secure In-Page Alternative:</strong><br/>
              Open the focused verification window without leaving this website. Your AutoApply session remains active right here in the background. Once solved, simply close the window and click <strong>Resume Automation</strong> below.
            </div>
            <div style="display: flex; gap: 10px; margin-top: 6px;">
              <button id="open-companion-win-btn" class="btn btn-primary btn-sm" style="padding: 10px 20px; font-weight: 500;">
                🗖 Open Secure Verification Window
              </button>
            </div>
          </div>
        `;

        document.getElementById('open-companion-win-btn').onclick = () => {
          const w = 880;
          const h = 760;
          const left = Math.max(0, (window.screen.width - w) / 2);
          const top = Math.max(0, (window.screen.height - h) / 2);
          window.open(
            targetUrl,
            'portal_verification',
            `width=${w},height=${h},top=${top},left=${left},status=no,toolbar=no,menubar=no,location=yes`
          );
        };
      }
    } catch (err) {
      // Fallback directly to sandbox iframe
      body.innerHTML = `
        <iframe
          id="inpage-active-frame"
          class="inpage-portal-frame"
          src="${targetUrl}"
          sandbox="allow-forms allow-scripts allow-same-origin allow-popups allow-modals"
          title="Embedded Portal View"
        ></iframe>
      `;
    }
  }

  function closeInPagePortal() {
    const overlay = document.getElementById('inpage-portal-overlay');
    if (overlay) overlay.style.display = 'none';
    const body = document.getElementById('inpage-portal-body');
    if (body) body.innerHTML = '';
  }

  // ---------------------------------------------------------------------------
  // Chat Visibility & Navigation
  // ---------------------------------------------------------------------------
  function updateVisibility() {
    const token = localStorage.getItem('token');
    const root = document.getElementById('ai-chatbot-root');
    if (!root) return;

    const hash = window.location.hash || '';
    const isAuthPage = hash === '#/login' || hash === '#/register';

    if (!token || isAuthPage) {
      root.style.display = 'none';
      stopPolling();
    } else {
      root.style.display = 'block';
      if (!_pollTimer) startPolling();
    }
  }

  function toggleChat() {
    if (_isOpen) closeChat();
    else openChat();
  }

  function openChat() {
    _isOpen = true;
    const win = document.getElementById('chatbot-window');
    const btn = document.getElementById('chatbot-toggle-btn');
    const badge = document.getElementById('chatbot-badge');

    if (win) win.style.display = 'flex';
    if (btn) btn.classList.add('open');
    if (badge) badge.style.display = 'none';

    scrollMessagesToBottom();
  }

  function closeChat() {
    _isOpen = false;
    const win = document.getElementById('chatbot-window');
    const btn = document.getElementById('chatbot-toggle-btn');

    if (win) win.style.display = 'none';
    if (btn) btn.classList.remove('open');
  }

  function startPolling() {
    stopPolling();
    checkAssistantStatus();
    _pollTimer = setInterval(checkAssistantStatus, 3000);
  }

  function stopPolling() {
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Real-Time Status & Live Step Progress Streaming
  // ---------------------------------------------------------------------------
  async function checkAssistantStatus() {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
      const data = await chatAPI.status();
      handleStatusUpdate(data);
    } catch (err) {
      // Silent fail
    }
  }

  function handleStatusUpdate(data) {
    const app = data.active_application;
    const banner = document.getElementById('chatbot-app-banner');
    const bannerText = document.getElementById('chatbot-banner-text');
    const bannerBadge = document.getElementById('chatbot-banner-badge');
    const statusDot = document.getElementById('chatbot-status-dot');
    const statusText = document.getElementById('chatbot-status-text');
    const badge = document.getElementById('chatbot-badge');

    if (!app) {
      if (banner) banner.style.display = 'none';
      if (statusDot) statusDot.className = 'chatbot-status-dot';
      if (statusText) statusText.textContent = 'Online • Ready';
      _currentAppId = null;
      _lastAppStatus = null;
      return;
    }

    _currentAppId = app.id;
    const status = app.status;
    const company = app.company || 'Job Application';

    // 1. Live Step Progress Streaming from recent_logs
    if (Array.isArray(app.recent_logs)) {
      app.recent_logs.forEach((log) => {
        if (log.id && !_renderedLogIds.has(log.id)) {
          _renderedLogIds.add(log.id);
          // Stream step message in chat while applying
          if (status === 'APPLYING' && log.level === 'INFO') {
            appendProgressStep(log.message);
          }
        }
      });
    }

    // 2. Banner updates
    if (banner && bannerText && bannerBadge) {
      banner.style.display = 'flex';
      if (status === 'APPLYING') {
        bannerText.innerHTML = `<span>🚀 Applying to <strong>${escapeHtml(company)}</strong></span>`;
        bannerBadge.innerHTML = `<span class="status-badge badge-warning">In Progress</span>`;
        if (statusDot) statusDot.className = 'chatbot-status-dot active';
        if (statusText) statusText.textContent = `Applying to ${company}…`;
      } else if (status === 'NEEDS_ACTION') {
        bannerText.innerHTML = `<span>⚠️ Action Needed for <strong>${escapeHtml(company)}</strong></span>`;
        bannerBadge.innerHTML = `<span class="status-badge badge-orange">Action Required</span>`;
        if (statusDot) statusDot.className = 'chatbot-status-dot active';
        if (statusText) statusText.textContent = 'Action Required';
      } else if (status === 'QUEUED') {
        bannerText.innerHTML = `<span>⏳ Queued for <strong>${escapeHtml(company)}</strong></span>`;
        bannerBadge.innerHTML = `<span class="status-badge badge-info">Queued</span>`;
        if (statusDot) statusDot.className = 'chatbot-status-dot';
        if (statusText) statusText.textContent = 'Queued';
      } else if (status === 'FAILED') {
        bannerText.innerHTML = `<span>❌ Issue with <strong>${escapeHtml(company)}</strong></span>`;
        bannerBadge.innerHTML = `<span class="status-badge badge-error">Failed</span>`;
        if (statusDot) statusDot.className = 'chatbot-status-dot';
        if (statusText) statusText.textContent = 'Paused / Error';
      } else if (status === 'APPLIED') {
        bannerText.innerHTML = `<span>✅ Submitted to <strong>${escapeHtml(company)}</strong></span>`;
        bannerBadge.innerHTML = `<span class="status-badge badge-success">Applied</span>`;
        if (statusDot) statusDot.className = 'chatbot-status-dot';
        if (statusText) statusText.textContent = 'Applied';
      }
    }

    // 3. Process Action Requirements (CAPTCHA, Login, OTP, Questions)
    const actionDetails = app.action_details || {};
    const actionType = actionDetails.type || '';
    const isNewAction = (status === 'NEEDS_ACTION' && (_lastAppStatus !== 'NEEDS_ACTION' || _lastActionType !== actionType));

    if (isNewAction) {
      _lastAppStatus = status;
      _lastActionType = actionType;

      // Pop open or show badge
      if (!_isOpen) {
        if (badge) badge.style.display = 'flex';
        openChat();
      }

      if (actionType === 'missing_info') {
        const missingFields = actionDetails.missing_fields || [];
        _activeMissingFields = missingFields;
        if (missingFields.length > 0) askMissingQuestions(app, missingFields);
      } else if (actionType === 'review_approval') {
        appendReviewApprovalAlert(app, actionDetails);
      } else if (actionType === 'captcha') {
        appendCaptchaAlert(app, actionDetails);
      } else if (actionType === 'login' || actionType === 'registration') {
        appendLoginAlert(app, actionDetails);
      } else if (actionType === 'otp') {
        appendOtpAlert(app, actionDetails);
      }
    } else if (status === 'FAILED' && _lastAppStatus !== 'FAILED') {
      _lastAppStatus = 'FAILED';
      if (!_isOpen) {
        if (badge) badge.style.display = 'flex';
        openChat();
      }
      appendFailureAlert(app);
    } else if (status === 'APPLIED' && _lastAppStatus !== 'APPLIED') {
      _lastAppStatus = 'APPLIED';
      appendBotMessage(`🎉 <strong>Congratulations!</strong> Your application for <strong>${escapeHtml(company)}</strong> has been successfully submitted!`);
    } else {
      _lastAppStatus = status;
    }
  }

  function appendProgressStep(message) {
    const container = document.getElementById('chatbot-messages');
    if (!container) return;

    // Filter noisy logs
    if (message.includes('Pipeline started') || message.includes('Navigating') || message.includes('Inspecting') || message.includes('AI mapped') || message.includes('Filling form')) {
      const stepEl = document.createElement('div');
      stepEl.className = 'chat-msg bot';
      stepEl.style.fontSize = '0.78rem';
      stepEl.style.padding = '6px 10px';
      stepEl.style.opacity = '0.88';
      stepEl.innerHTML = `⚙️ <em>${escapeHtml(message)}</em>`;
      container.appendChild(stepEl);
      scrollMessagesToBottom();
    }
  }

  // ---------------------------------------------------------------------------
  // Missing Questions Interaction
  // ---------------------------------------------------------------------------
  function askMissingQuestions(app, missingFields) {
    const company = escapeHtml(app.company || 'the job');
    appendBotMessage(`Notice for your application to <strong>${company}</strong>: The employer requires additional information not yet in your profile:`);
    const q = missingFields[0];
    appendQuestionCard(app.id, q, missingFields.length);
  }

  function appendQuestionCard(appId, field, totalRemaining) {
    const container = document.getElementById('chatbot-messages');
    if (!container) return;

    const card = document.createElement('div');
    card.className = 'chat-msg bot';
    card.id = `chat-q-${field.key}`;

    const label = escapeHtml(field.label || field.key);
    let interactiveHtml = '';

    if (field.type === 'yes_no') {
      interactiveHtml = `
        <div class="chat-options-grid">
          <button class="chat-opt-btn btn-choice" data-val="Yes">Yes</button>
          <button class="chat-opt-btn btn-choice" data-val="No">No</button>
        </div>
      `;
    } else if (field.type === 'select' && field.options && field.options.length > 0) {
      const optButtons = field.options.map(opt => `
        <button class="chat-opt-btn btn-choice" data-val="${escapeHtml(opt)}">${escapeHtml(opt)}</button>
      `).join('');
      interactiveHtml = `<div class="chat-options-grid">${optButtons}</div>`;
    } else {
      interactiveHtml = `
        <div style="display: flex; gap: 6px; margin-top: 4px;">
          <input
            type="${field.type === 'number' ? 'number' : 'text'}"
            class="chatbot-input chat-direct-input"
            placeholder="Type your answer…"
            style="border-radius: 6px; padding: 6px 10px; font-size: 0.82rem;"
          />
          <button class="btn btn-primary btn-xs btn-submit-direct" style="padding: 6px 12px; font-size: 0.78rem;">Save</button>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="chat-question-card">
        <div class="chat-question-header">
          <span class="chat-question-label">❓ ${label}</span>
          <span style="font-size: 0.72rem; color: var(--text-muted);">${totalRemaining} remaining</span>
        </div>
        <div>${interactiveHtml}</div>
        <div style="display: flex; align-items: center; gap: 6px; font-size: 0.74rem; color: var(--text-secondary); margin-top: 4px;">
          <input type="checkbox" id="save-profile-${field.key}" checked style="accent-color: var(--accent); cursor: pointer;" />
          <label for="save-profile-${field.key}" style="cursor: pointer;">Save answer to profile for future applications</label>
        </div>
      </div>
    `;

    container.appendChild(card);
    scrollMessagesToBottom();

    // Bind choices
    card.querySelectorAll('.btn-choice').forEach(btn => {
      btn.addEventListener('click', async () => {
        const val = btn.dataset.val;
        const saveProfile = card.querySelector(`#save-profile-${field.key}`)?.checked ?? true;
        await submitQuestionAnswer(appId, field.key, val, saveProfile, card);
      });
    });

    // Bind direct input
    const submitBtn = card.querySelector('.btn-submit-direct');
    const inputEl = card.querySelector('.chat-direct-input');
    if (submitBtn && inputEl) {
      const doSubmit = async () => {
        const val = inputEl.value.trim();
        if (!val) return;
        const saveProfile = card.querySelector(`#save-profile-${field.key}`)?.checked ?? true;
        await submitQuestionAnswer(appId, field.key, val, saveProfile, card);
      };
      submitBtn.addEventListener('click', doSubmit);
      inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          doSubmit();
        }
      });
    }
  }

  async function submitQuestionAnswer(appId, fieldKey, answer, saveToProfile, cardEl) {
    if (cardEl) {
      cardEl.querySelectorAll('button, input').forEach(el => el.disabled = true);
      cardEl.style.opacity = '0.75';
    }

    appendUserMessage(answer);

    try {
      const res = await chatAPI.answer(appId, fieldKey, answer, saveToProfile);
      if (res.resumed) {
        appendBotMessage(`🎉 <strong>All questions answered!</strong> Resuming your application for <strong>${escapeHtml(res.application?.company || 'the job')}</strong> now 🚀`);
      } else if (res.next_question) {
        appendBotMessage(`Saved answer for <em>${escapeHtml(fieldKey)}</em>. Next question:`);
        appendQuestionCard(appId, res.next_question, res.remaining_count);
      } else {
        appendBotMessage(`Answer saved successfully!`);
      }
    } catch (err) {
      appendBotMessage(`⚠️ Could not save answer: ${err.message}. Please try again.`);
      if (cardEl) {
        cardEl.querySelectorAll('button, input').forEach(el => el.disabled = false);
        cardEl.style.opacity = '1';
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Action Alerts: Review Approval, CAPTCHA, Sign-In, OTP, Failure
  // ---------------------------------------------------------------------------
  function appendReviewApprovalAlert(app, details) {
    const company = escapeHtml(app.company || 'Employer');
    const role = escapeHtml(app.role || 'Job Application');
    const summary = details.summary || {};
    const ssUrl = details.screenshot_url || app.screenshot_url;

    let summaryItems = '';
    const keys = Object.keys(summary);
    if (keys.length > 0) {
      summaryItems = '<div style="margin: 8px 0; background: var(--bg-card); padding: 8px 10px; border-radius: 6px; font-size: 0.8rem; border: 1px solid var(--border); max-height: 140px; overflow-y: auto;">';
      for (const k of keys.slice(0, 10)) {
        summaryItems += `<div><strong>${escapeHtml(k)}:</strong> <span style="color: var(--accent);">${escapeHtml(summary[k])}</span></div>`;
      }
      summaryItems += '</div>';
    }

    const ssLink = ssUrl ? `<div style="margin-top: 6px;"><a href="${ssUrl}" target="_blank" style="font-size: 0.78rem; color: var(--accent); text-decoration: underline;">📸 View Filled Review Screenshot</a></div>` : '';

    const html = `
      <div class="chat-action-card" style="border-left: 3px solid var(--success);">
        <div style="font-weight: 600; color: var(--success); display: flex; align-items: center; gap: 6px;">
          <span>📋</span> Application Review Ready
        </div>
        <div style="color: var(--text-secondary); line-height: 1.45; font-size: 0.83rem;">
          All fields for <strong>${role}</strong> at <strong>${company}</strong> have been accurately filled and validated. Please review before final submission:
        </div>
        ${summaryItems}
        ${ssLink}
        <div style="margin-top: 10px;">
          <button class="btn btn-primary btn-sm approve-action-btn" data-id="${app.id}" style="width: 100%; padding: 8px 12px; font-size: 0.85rem; background: var(--success); border-color: var(--success);">
            🚀 Approve & Submit Application
          </button>
        </div>
      </div>
    `;
    appendBotMessage(html, true);
    bindActionButtons();
  }

  function appendCaptchaAlert(app, details) {
    const company = escapeHtml(app.company || 'Job Portal');
    const targetUrl = details.url || app.url;

    const html = `
      <div class="chat-action-card">
        <div style="font-weight: 600; color: var(--warning); display: flex; align-items: center; gap: 6px;">
          <span>🛡️</span> Security Verification Challenge Detected
        </div>
        <div style="color: var(--text-secondary); line-height: 1.45;">
          Automation is paused on <strong>${company}</strong> so you can solve the CAPTCHA. You do not need to leave the site:
        </div>
        <div class="chat-action-buttons" style="margin-top: 6px;">
          <button class="btn btn-primary btn-sm open-inpage-action-btn" data-id="${app.id}" data-company="${escapeHtml(company)}" data-url="${targetUrl}" data-action="captcha" style="padding: 6px 12px; font-size: 0.8rem;">
            🛡️ Solve Inside App (In-Page View)
          </button>
          <button class="btn btn-success btn-sm resume-action-btn" data-id="${app.id}" style="padding: 6px 12px; font-size: 0.8rem;">
            ▶️ I've Solved It — Resume
          </button>
        </div>
      </div>
    `;
    appendBotMessage(html, true);
    bindActionButtons();
  }

  function appendLoginAlert(app, details) {
    const company = escapeHtml(app.company || 'Job Portal');
    const targetUrl = details.url || app.url;

    const html = `
      <div class="chat-action-card">
        <div style="font-weight: 600; color: var(--warning); display: flex; align-items: center; gap: 6px;">
          <span>🔐</span> Candidate Sign-In Required
        </div>
        <div style="color: var(--text-secondary); line-height: 1.45;">
          <strong>${company}</strong> requires candidate authentication to submit. You can complete sign-in right here:
        </div>
        <div class="chat-action-buttons" style="margin-top: 6px;">
          <button class="btn btn-primary btn-sm open-inpage-action-btn" data-id="${app.id}" data-company="${escapeHtml(company)}" data-url="${targetUrl}" data-action="login" style="padding: 6px 12px; font-size: 0.8rem;">
            🔐 Sign In Inside App (In-Page View)
          </button>
          <button class="btn btn-success btn-sm resume-action-btn" data-id="${app.id}" style="padding: 6px 12px; font-size: 0.8rem;">
            ▶️ I've Logged In — Resume
          </button>
        </div>
      </div>
    `;
    appendBotMessage(html, true);
    bindActionButtons();
  }

  function appendOtpAlert(app, details) {
    const company = escapeHtml(app.company || 'Job Portal');
    const targetUrl = details.url || app.url;

    const html = `
      <div class="chat-otp-card">
        <div style="font-weight: 600; color: var(--warning); display: flex; align-items: center; gap: 6px;">
          <span>📲</span> Verification Code / OTP Required
        </div>
        <div style="color: var(--text-secondary); line-height: 1.45; font-size: 0.82rem;">
          The portal requested a security code sent to your email or phone for <strong>${company}</strong>.
        </div>
        <div style="display: flex; gap: 6px; margin-top: 4px;">
          <input
            type="text"
            class="chatbot-input inchat-otp-input"
            placeholder="Enter code (e.g. 123456)"
            style="border-radius: 6px; padding: 6px 10px; font-size: 0.85rem; letter-spacing: 2px;"
          />
          <button class="btn btn-primary btn-xs inchat-submit-otp" data-id="${app.id}" style="padding: 6px 12px; font-size: 0.78rem;">
            Submit & Resume
          </button>
        </div>
        <div style="margin-top: 6px; display: flex; gap: 8px;">
          <button class="btn btn-outline btn-xs open-inpage-action-btn" data-id="${app.id}" data-company="${escapeHtml(company)}" data-url="${targetUrl}" data-action="otp" style="font-size: 0.75rem; padding: 4px 8px;">
            🛡️ Open In-Page View
          </button>
          <button class="btn btn-success btn-xs resume-action-btn" data-id="${app.id}" style="font-size: 0.75rem; padding: 4px 8px;">
            ▶️ Verification Done — Resume
          </button>
        </div>
      </div>
    `;
    appendBotMessage(html, true);
    bindActionButtons();
  }

  function appendFailureAlert(app) {
    const company = escapeHtml(app.company || 'Job Application');
    const errText = escapeHtml(app.error_message || 'An unexpected issue occurred during submission.');

    const html = `
      <div class="chat-error-card">
        <div style="font-weight: 600; color: var(--error); display: flex; align-items: center; gap: 6px;">
          <span>❌</span> Application Paused / Error
        </div>
        <div style="font-size: 0.82rem; color: var(--text-primary); line-height: 1.45;">
          ${errText}
        </div>
        <div style="margin-top: 4px;">
          <button class="btn btn-warning btn-sm inchat-retry-btn" data-id="${app.id}" style="padding: 6px 12px; font-size: 0.8rem;">
            🔄 Retry Application
          </button>
        </div>
      </div>
    `;
    appendBotMessage(html, true);
    bindActionButtons();
  }

  function bindActionButtons() {
    const container = document.getElementById('chatbot-messages');
    if (!container) return;

    // 1. Open In-Page Embedded Portal Modal
    container.querySelectorAll('.open-inpage-action-btn:not(.bound)').forEach(btn => {
      btn.classList.add('bound');
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const appId = btn.dataset.id;
        const company = btn.dataset.company;
        const targetUrl = btn.dataset.url;
        const actionType = btn.dataset.action;
        openInPagePortal(appId, company, targetUrl, actionType);
      });
    });

    // 2. Resume Buttons
    container.querySelectorAll('.resume-action-btn:not(.bound)').forEach(btn => {
      btn.classList.add('bound');
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const appId = btn.dataset.id;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Resuming…';

        try {
          const res = await chatAPI.resume(appId);
          appendBotMessage(`🚀 Resuming your application for <strong>${escapeHtml(res.application?.company || 'the job')}</strong>! I'm monitoring the process...`);
          startPolling();
        } catch (err) {
          appendBotMessage(`⚠️ Could not resume: ${err.message}. Please click again.`);
          btn.disabled = false;
          btn.textContent = '▶️ Try Resuming Again';
        }
      });
    });

    // 3. In-Chat OTP Submit
    container.querySelectorAll('.inchat-submit-otp:not(.bound)').forEach(btn => {
      btn.classList.add('bound');
      const card = btn.closest('.chat-otp-card');
      const inputEl = card ? card.querySelector('.inchat-otp-input') : null;

      const doSubmitOtp = async () => {
        const code = inputEl ? inputEl.value.trim() : '';
        if (!code) return;
        const appId = btn.dataset.id;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Submitting…';

        try {
          await chatAPI.answer(appId, 'verification_code', code, false);
          appendBotMessage(`📲 Verification code <strong>${escapeHtml(code)}</strong> submitted! Resuming application now 🚀`);
          startPolling();
        } catch (err) {
          appendBotMessage(`⚠️ Could not submit code: ${err.message}`);
          btn.disabled = false;
          btn.textContent = 'Submit Code';
        }
      };

      btn.addEventListener('click', doSubmitOtp);
      if (inputEl) {
        inputEl.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            doSubmitOtp();
          }
        });
      }
    });

    // 4. In-Chat Review Approval Button
    container.querySelectorAll('.approve-action-btn:not(.bound)').forEach(btn => {
      btn.classList.add('bound');
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const appId = btn.dataset.id;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Submitting…';
        appendUserMessage('🚀 Approve & Submit Application');

        try {
          await applicationsAPI.approve(appId);
          appendBotMessage(`🚀 <strong>Application Approved!</strong> Submitting now. Monitoring for submission confirmation receipt...`);
          startPolling();
        } catch (err) {
          appendBotMessage(`⚠️ Approval failed: ${err.message}. Please click again.`);
          btn.disabled = false;
          btn.textContent = '🚀 Approve & Submit Application';
        }
      });
    });

    // 5. In-Chat Retry Button
    container.querySelectorAll('.inchat-retry-btn:not(.bound)').forEach(btn => {
      btn.classList.add('bound');
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const appId = btn.dataset.id;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Retrying…';

        try {
          await chatAPI.retry(appId);
          appendBotMessage(`🔄 Retrying application now! I will monitor the steps and report progress here.`);
          startPolling();
        } catch (err) {
          appendBotMessage(`⚠️ Retry failed: ${err.message}`);
          btn.disabled = false;
          btn.textContent = '🔄 Retry Application';
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // User Chat Input
  // ---------------------------------------------------------------------------
  async function handleUserInput(e) {
    e.preventDefault();
    const input = document.getElementById('chatbot-input-field');
    const btn = document.getElementById('chatbot-send-btn');
    const text = input.value.trim();
    if (!text) return;

    appendUserMessage(text);
    input.value = '';
    btn.disabled = true;

    try {
      const res = await chatAPI.sendMessage(text);
      if (res && res.reply) {
        appendBotMessage(res.reply);
      }
      if (res && res.action === 'application_started') {
        startPolling();
      }
    } catch (err) {
      appendBotMessage(`Sorry, I encountered an error: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  }

  function appendBotMessage(text, isHtml = false) {
    const container = document.getElementById('chatbot-messages');
    if (!container) return;

    const el = document.createElement('div');
    el.className = 'chat-msg bot';
    if (isHtml) {
      el.innerHTML = text;
    } else {
      let formatted = escapeHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>')
        .replace(/\n/g, '<br/>');
      el.innerHTML = formatted;
    }

    container.appendChild(el);
    scrollMessagesToBottom();
  }

  function appendUserMessage(text) {
    const container = document.getElementById('chatbot-messages');
    if (!container) return;

    const el = document.createElement('div');
    el.className = 'chat-msg user';
    el.textContent = text;
    container.appendChild(el);
    scrollMessagesToBottom();
  }

  function scrollMessagesToBottom() {
    const container = document.getElementById('chatbot-messages');
    if (container) container.scrollTop = container.scrollHeight;
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  return { init, openChat, closeChat, checkAssistantStatus, openInPagePortal };
})();

// Initialize chatbot when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', AIChatbot.init);
} else {
  AIChatbot.init();
}
