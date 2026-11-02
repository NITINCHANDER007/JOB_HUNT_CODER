/**
 * AutoApply AI — Settings Page
 * LinkedIn session, Gmail connection, password change, account management.
 */

const SettingsPage = (() => {
  let _linkedinPollTimer = null;

  async function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1>Settings</h1>
        <p class="text-muted">Manage your account, browser sessions, and integrations</p>
      </div>

      <!-- LinkedIn Session & Automation Profile -->
      <div class="card" style="border-left: 4px solid var(--accent, #6366f1);">
        <h3 class="card-title">💼 LinkedIn Easy Apply & Browser Session</h3>
        <p class="text-muted" style="margin-bottom: 16px;">
          Log into LinkedIn manually once using your own browser session. We reuse your authenticated persistent session across all Easy Apply applications without asking for your password.
        </p>

        <div id="linkedin-status-container">
          <div class="spinner-sm"></div> Checking LinkedIn session…
        </div>

        <div style="margin-top: 20px; border-top: 1px solid var(--border); padding-top: 16px;">
          <h4 style="margin: 0 0 12px 0; font-size: 0.95rem;">Automation Preferences</h4>
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <label style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer; font-size: 0.88rem;">
              <input type="checkbox" id="pref-headed-mode" style="margin-top: 3px;" />
              <span><strong>Show browser window while running:</strong> Opens a visible Chrome window so you can watch field filling and automation live on your desktop.</span>
            </label>
            <label style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer; font-size: 0.88rem;">
              <input type="checkbox" id="pref-require-approval" checked style="margin-top: 3px;" />
              <span><strong>Require final approval before submit:</strong> Pauses at the final Review step so you can review filled answers in the chatbot/dashboard before final submission.</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Gmail Integration -->
      <div class="card">
        <h3 class="card-title">📧 Gmail Integration</h3>
        <p class="text-muted" style="margin-bottom: 16px;">
          Connect your Gmail (read-only) to automatically detect job application
          confirmation emails and link them to your applications.
        </p>
        <div id="gmail-status">
          <div class="spinner-sm"></div> Checking connection…
        </div>
      </div>

      <!-- Security -->
      <div class="card">
        <h3 class="card-title">🔒 Change Password</h3>
        <form id="change-password-form" class="settings-form">
          <div class="form-group">
            <label for="current-password">Current Password</label>
            <input type="password" id="current-password" required autocomplete="current-password" />
          </div>
          <div class="form-group">
            <label for="new-password">New Password</label>
            <input type="password" id="new-password" required autocomplete="new-password"
                   placeholder="Min 8 chars, 1 letter, 1 number" />
          </div>
          <div class="form-group">
            <label for="confirm-new-password">Confirm New Password</label>
            <input type="password" id="confirm-new-password" required autocomplete="new-password" />
          </div>
          <button type="submit" class="btn btn-primary" id="change-pw-btn">Update Password</button>
        </form>
      </div>

      <!-- Rate Limiting Info -->
      <div class="card">
        <h3 class="card-title">📊 Usage Limits</h3>
        <div id="rate-limit-info">
          <div class="spinner-sm"></div> Loading…
        </div>
      </div>

      <!-- Danger Zone -->
      <div class="card card-danger">
        <h3 class="card-title">⚠️ Danger Zone</h3>
        <p class="text-muted" style="margin-bottom: 16px;">
          Permanently delete your account and all associated data. This action cannot be undone.
        </p>
        <button class="btn btn-error" id="delete-account-btn">Delete Account</button>
      </div>
    `;

    // Check for URL params (Gmail callback redirect)
    checkGmailCallback();

    // Load LinkedIn status & preferences
    loadLinkedInStatus();

    // Load Gmail status
    loadGmailStatus();

    // Load rate limit info
    loadRateLimitInfo();

    // Change password
    document.getElementById('change-password-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('change-pw-btn');
      const current = document.getElementById('current-password').value;
      const newPw = document.getElementById('new-password').value;
      const confirm = document.getElementById('confirm-new-password').value;

      if (newPw !== confirm) {
        showToast('New passwords do not match', 'error');
        return;
      }
      if (newPw.length < 8) {
        showToast('Password must be at least 8 characters', 'warning');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Updating…';

      try {
        await authAPI.changePassword(current, newPw);
        showToast('Password updated successfully', 'success');
        document.getElementById('change-password-form').reset();
      } catch (err) {
        showToast(err.message || 'Failed to change password', 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Update Password';
      }
    });

    // Delete account
    document.getElementById('delete-account-btn').addEventListener('click', async () => {
      const confirmed = confirm(
        'Are you sure you want to delete your account?\n\n' +
        'This will permanently delete:\n' +
        '• Your profile and all personal data\n' +
        '• All application records and screenshots\n' +
        '• All uploaded resumes\n\n' +
        'This action CANNOT be undone.'
      );
      if (!confirmed) return;

      try {
        await authAPI.deleteAccount();
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        showToast('Account deleted', 'info');
        window.location.hash = '#/login';
      } catch (err) {
        showToast(err.message || 'Failed to delete account', 'error');
      }
    });
  }

  // ---------------------------------------------------------------------------
  // LinkedIn Session Management
  // ---------------------------------------------------------------------------

  async function loadLinkedInStatus() {
    const container = document.getElementById('linkedin-status-container');
    const prefHeaded = document.getElementById('pref-headed-mode');
    const prefApproval = document.getElementById('pref-require-approval');
    if (!container) return;

    try {
      const data = await linkedinAPI.status();

      // Update preference checkboxes
      if (prefHeaded) {
        prefHeaded.checked = !data.headless;
        prefHeaded.onchange = async () => {
          await linkedinAPI.updateSettings({ headless: !prefHeaded.checked });
          showToast(`Browser visibility updated: ${prefHeaded.checked ? 'Visible window' : 'Headless'}`, 'info');
        };
      }

      if (prefApproval) {
        prefApproval.checked = Boolean(data.require_approval);
        prefApproval.onchange = async () => {
          await linkedinAPI.updateSettings({ require_approval: prefApproval.checked });
          showToast(`Pre-submission approval requirement: ${prefApproval.checked ? 'Enabled' : 'Disabled'}`, 'info');
        };
      }

      if (data.connected) {
        const expiresText = data.days_remaining !== null
          ? `${data.days_remaining} days remaining`
          : 'Active';

        container.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.2); border-radius: var(--radius-sm); padding: 14px 18px;">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="status-dot status-dot-green"></span>
                <strong style="color: var(--success); font-size: 0.95rem;">LinkedIn Connected</strong>
                <span style="font-size: 0.8rem; color: var(--text-secondary);">(${escapeHtml(expiresText)})</span>
              </div>
              <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">
                Authenticated as: <strong>${escapeHtml(data.user_name || 'LinkedIn Member')}</strong>
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-sm btn-ghost" id="li-verify-btn">🔍 Verify Session</button>
              <button class="btn btn-sm btn-error" id="li-disconnect-btn">Disconnect</button>
            </div>
          </div>
        `;

        document.getElementById('li-verify-btn').addEventListener('click', async () => {
          const btn = document.getElementById('li-verify-btn');
          btn.disabled = true;
          btn.textContent = 'Verifying…';
          try {
            const res = await linkedinAPI.verify();
            if (res.valid) {
              showToast('LinkedIn session verified successfully! Ready for applications.', 'success');
            } else {
              showToast(`Session invalid: ${res.message}`, 'error');
              loadLinkedInStatus();
            }
          } catch (err) {
            showToast('Verification check error: ' + err.message, 'error');
          } finally {
            btn.disabled = false;
            btn.textContent = '🔍 Verify Session';
          }
        });

        document.getElementById('li-disconnect-btn').addEventListener('click', async () => {
          if (!confirm('Disconnect your saved LinkedIn session? You will need to log in again to use Easy Apply.')) return;
          try {
            await linkedinAPI.disconnect();
            showToast('LinkedIn session disconnected', 'info');
            loadLinkedInStatus();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });

      } else {
        container.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: var(--radius-sm); padding: 14px 18px;">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="status-dot status-dot-gray"></span>
                <strong style="color: var(--warning, #f59e0b); font-size: 0.95rem;">LinkedIn Not Connected</strong>
              </div>
              <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">
                Click below to open a browser window and log into your LinkedIn account manually once.
              </div>
            </div>
            <button class="btn btn-primary btn-sm" id="li-connect-btn">
              🔗 Connect LinkedIn
            </button>
          </div>
          <div id="li-login-progress" style="margin-top: 10px; display: none;"></div>
        `;

        document.getElementById('li-connect-btn').addEventListener('click', startInteractiveLogin);
      }

    } catch (err) {
      container.innerHTML = `<p class="text-error">Failed to load LinkedIn session status: ${err.message}</p>`;
    }
  }

  async function startInteractiveLogin() {
    const btn = document.getElementById('li-connect-btn');
    const progress = document.getElementById('li-login-progress');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-sm"></span> Launching Chrome…';
    }
    if (progress) {
      progress.style.display = 'block';
      progress.innerHTML = `
        <div style="padding: 12px 16px; background: var(--bg-card); border: 1px solid var(--accent); border-radius: var(--radius-sm); font-size: 0.85rem;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="spinner-sm"></span>
              <strong id="li-progress-title">Launching Chrome browser on your desktop…</strong>
            </div>
            <button class="btn btn-xs btn-ghost text-muted" id="li-cancel-btn" style="padding: 2px 8px; font-size: 0.75rem;">Cancel</button>
          </div>
          <div id="li-progress-msg" style="color: var(--text-secondary); line-height: 1.4;">
            Preparing browser profile and launching Chrome window...
          </div>
          <div id="li-status-detail" style="font-weight: 500; color: #38bdf8; margin-top: 6px; font-size: 0.8rem;">
            Connecting to browser process...
          </div>
        </div>
      `;

      const cancelBtn = progress.querySelector('#li-cancel-btn');
      if (cancelBtn) {
        cancelBtn.addEventListener('click', async () => {
          if (_linkedinPollTimer) {
            clearInterval(_linkedinPollTimer);
            _linkedinPollTimer = null;
          }
          try {
            await linkedinAPI.cancelLogin();
          } catch (e) {
            // ignore
          }
          showToast('LinkedIn login cancelled', 'info');
          loadLinkedInStatus();
        });
      }
    }

    try {
      const connectRes = await linkedinAPI.connect();

      // If backend returned error directly
      if (connectRes.status === 'error' || connectRes.error) {
        throw new Error(connectRes.error || connectRes.message || 'Failed to launch Chrome');
      }

      // Update message once confirmed
      const titleEl = progress ? progress.querySelector('#li-progress-title') : null;
      const msgEl = progress ? progress.querySelector('#li-progress-msg') : null;
      const detailEl = progress ? progress.querySelector('#li-status-detail') : null;

      if (connectRes.browser_verified && titleEl) {
        titleEl.textContent = 'Chrome browser window is open on your desktop!';
        if (msgEl) msgEl.textContent = 'Please log into LinkedIn in the opened Chrome window. Automation will automatically detect your login.';
      }
      if (connectRes.message && detailEl) {
        detailEl.textContent = connectRes.message;
      }

      // Start polling for login completion
      if (_linkedinPollTimer) clearInterval(_linkedinPollTimer);
      _linkedinPollTimer = setInterval(async () => {
        try {
          const res = await linkedinAPI.connectStatus();
          const interactive = res.interactive || {};
          const session = res.session || {};

          if (progress) {
            const detail = progress.querySelector('#li-status-detail');
            const title = progress.querySelector('#li-progress-title');
            const msg = progress.querySelector('#li-progress-msg');

            if (interactive.message && detail) {
              detail.textContent = interactive.message;
            }

            if (interactive.browser_verified && title && !title.textContent.includes('open')) {
              title.textContent = 'Chrome browser window is open on your desktop!';
              if (msg) msg.textContent = 'Please log into LinkedIn in the opened Chrome window. Automation will automatically detect your login.';
            }
          }

          if (session.connected || interactive.status === 'success') {
            clearInterval(_linkedinPollTimer);
            _linkedinPollTimer = null;
            showToast('LinkedIn login successful! Your persistent session is saved 🎉', 'success');
            loadLinkedInStatus();
          } else if (interactive.status === 'timed_out') {
            clearInterval(_linkedinPollTimer);
            _linkedinPollTimer = null;
            showToast(interactive.message || 'Login timed out or window was closed', 'warning');
            loadLinkedInStatus();
          } else if (interactive.status === 'error') {
            clearInterval(_linkedinPollTimer);
            _linkedinPollTimer = null;
            showToast('Chrome launch error: ' + (interactive.error || interactive.message), 'error');
            if (progress) {
              progress.innerHTML = `
                <div style="padding: 10px 14px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius-sm); font-size: 0.85rem; color: #ef4444;">
                  <strong>Could not launch Chrome:</strong> ${escapeHtml(interactive.error || interactive.message)}
                </div>
              `;
            }
            if (btn) {
              btn.disabled = false;
              btn.textContent = '🔗 Connect LinkedIn';
            }
          }
        } catch (e) {
          // ignore transient poll error
        }
      }, 2000);

    } catch (err) {
      if (_linkedinPollTimer) {
        clearInterval(_linkedinPollTimer);
        _linkedinPollTimer = null;
      }
      showToast('Failed to start LinkedIn connection: ' + err.message, 'error');
      if (progress) {
        progress.innerHTML = `
          <div style="padding: 10px 14px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius-sm); font-size: 0.85rem; color: #ef4444;">
            <strong>Launch Failed:</strong> ${escapeHtml(err.message)}
          </div>
        `;
      }
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🔗 Connect LinkedIn';
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Gmail & Limits
  // ---------------------------------------------------------------------------

  function checkGmailCallback() {
    const hash = window.location.hash;
    if (hash.includes('gmail_connected=true') || hash.includes('gmail=success')) {
      showToast('Gmail connected successfully!', 'success');
      window.location.hash = '#/settings';
      loadGmailStatus();
    } else if (hash.includes('gmail_error=') || hash.includes('gmail=error')) {
      const match = hash.match(/gmail_error=([^&]*)/) || hash.match(/reason=([^&]*)/);
      const errMsg = match ? decodeURIComponent(match[1]) : 'unknown error';
      showToast('Gmail connection failed: ' + errMsg, 'error');
      window.location.hash = '#/settings';
      loadGmailStatus();
    }
  }

  async function loadGmailStatus() {
    const container = document.getElementById('gmail-status');
    if (!container) return;

    try {
      const status = await gmailAPI.status();

      if (status.connected) {
        container.innerHTML = `
          <div class="gmail-connected">
            <span class="status-dot status-dot-green"></span>
            <span>Connected as <strong>${escapeHtml(status.email || 'your Gmail')}</strong></span>
          </div>
          <div class="gmail-actions" style="margin-top: 12px;">
            <button class="btn btn-sm btn-ghost" id="gmail-sync-btn">🔄 Sync Now</button>
            <button class="btn btn-sm btn-error" id="gmail-disconnect-btn">Disconnect</button>
          </div>
        `;

        document.getElementById('gmail-sync-btn').addEventListener('click', async () => {
          try {
            const result = await gmailAPI.sync();
            showToast(result.message || 'Gmail sync started', 'success');
          } catch (err) {
            showToast(err.message, 'error');
          }
        });

        document.getElementById('gmail-disconnect-btn').addEventListener('click', async () => {
          if (!confirm('Disconnect Gmail?')) return;
          try {
            await gmailAPI.disconnect();
            showToast('Gmail disconnected', 'info');
            loadGmailStatus();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      } else if (status.configured === false) {
        container.innerHTML = `
          <div class="gmail-disconnected">
            <span class="status-dot status-dot-gray"></span>
            <span>Not Connected &bull; <strong style="color: #f59e0b;">OAuth Not Configured</strong></span>
          </div>
          <p class="text-xs text-muted" style="margin-top: 8px; line-height: 1.4;">
            To connect Gmail, configure <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> in your <code>.env</code> file with redirect URI <code>${escapeHtml(status.redirect_uri || 'http://localhost:5050/api/gmail/callback')}</code>.
          </p>
          <button class="btn btn-primary btn-sm" id="gmail-connect-btn" style="margin-top: 10px;">
            Connect Gmail
          </button>
        `;

        document.getElementById('gmail-connect-btn').addEventListener('click', async () => {
          try {
            const data = await gmailAPI.authUrl();
            if (data.auth_url) {
              window.open(data.auth_url, '_blank', 'width=600,height=700');
            } else {
              showToast(data.error || 'Google OAuth is not configured in .env', 'error');
            }
          } catch (err) {
            showToast(err.message || 'Google OAuth is not configured in .env', 'error');
          }
        });
      } else {
        container.innerHTML = `
          <div class="gmail-disconnected">
            <span class="status-dot status-dot-gray"></span>
            <span>Not connected</span>
          </div>
          <button class="btn btn-primary btn-sm" id="gmail-connect-btn" style="margin-top: 12px;">
            Connect Gmail
          </button>
        `;

        document.getElementById('gmail-connect-btn').addEventListener('click', async () => {
          try {
            const data = await gmailAPI.authUrl();
            if (data.auth_url) {
              window.open(data.auth_url, '_blank', 'width=600,height=700');
            } else {
              showToast(data.error || 'Failed to start Gmail auth', 'error');
            }
          } catch (err) {
            showToast('Failed to start Gmail auth: ' + err.message, 'error');
          }
        });
      }
    } catch (err) {
      container.innerHTML = `<p class="text-error">Failed to load Gmail status: ${escapeHtml(err.message || '')}</p>`;
    }
  }

  async function loadRateLimitInfo() {
    const container = document.getElementById('rate-limit-info');
    if (!container) return;

    try {
      const data = await applicationsAPI.list({ per_page: 1 });
      const used = data.count_today || 0;
      const limit = data.limit || 50;

      container.innerHTML = `
        <div class="rate-info-grid">
          <div>
            <strong>Daily Application Limit:</strong> ${limit}
          </div>
          <div>
            <strong>Used Today:</strong> ${used}
          </div>
          <div>
            <strong>Remaining:</strong> ${limit - used}
          </div>
        </div>
        <p class="text-muted" style="margin-top: 12px;">
          The daily limit resets at midnight UTC. Applications are rate-limited to
          prevent abuse and avoid detection by ATS platforms.
        </p>
      `;
    } catch (err) {
      container.innerHTML = '<p class="text-muted">Could not load usage info.</p>';
    }
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  return { render };
})();
