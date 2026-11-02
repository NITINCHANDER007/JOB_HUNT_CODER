/**
 * AutoApply AI — Apply Page
 * Job URL input, submission, LinkedIn session indicator,
 * recent applications list, review approval, rate limit display.
 */

const ApplyPage = (() => {
  let _isProfileComplete = false;
  let _isLinkedInConnected = false;
  let _pollInterval = null;

  function stopPolling() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  function startPolling() {
    stopPolling();
    _pollInterval = setInterval(async () => {
      if (!document.getElementById('recent-apps')) {
        stopPolling();
        return;
      }
      await loadRecentApps(true);
    }, 3500);
  }

  async function render(container) {
    stopPolling();
    container.innerHTML = `
      <div class="page-header">
        <h1>Apply to a Job</h1>
        <p class="text-muted">Paste a job application link and we'll handle the rest</p>
      </div>

      <!-- Completeness Gate Banner -->
      <div id="profile-gate-banner"></div>

      <!-- LinkedIn Session Status Pill -->
      <div id="linkedin-status-pill" style="margin-bottom: 16px;"></div>

      <!-- Rate limit info -->
      <div class="rate-limit-bar" id="rate-limit-bar">
        <span class="spinner-sm"></span> Loading usage…
      </div>

      <!-- Apply Form -->
      <div class="card apply-card">
        <form id="apply-form">
          <div class="apply-input-group">
            <input
              type="url"
              id="job-url-input"
              class="apply-input"
              placeholder="https://www.linkedin.com/jobs/view/12345 or https://boards.greenhouse.io/..."
              required
              autocomplete="url"
            />
            <button type="submit" class="btn btn-primary btn-lg" id="apply-btn">
              🚀 Apply
            </button>
          </div>
          <p class="apply-hint text-muted">
            Supports: LinkedIn Easy Apply (with your saved browser session), Greenhouse, Lever, Ashby, Workday, SmartRecruiters, ByteDance, and company career pages
          </p>
        </form>
      </div>

      <!-- Recent Applications -->
      <div class="card" style="margin-top: 24px;">
        <h3 class="card-title">Recent Applications</h3>
        <div id="recent-apps">
          <div class="page-loading"><div class="spinner-sm"></div></div>
        </div>
      </div>
    `;

    // Check profile completeness & enforce gate
    await checkProfileCompleteness();

    // Check LinkedIn session status
    await checkLinkedInSession();

    // Load rate limit and recent apps
    loadRateLimit();
    loadRecentApps();

    // Form submission
    document.getElementById('apply-form').addEventListener('submit', async (e) => {
      e.preventDefault();

      if (!_isProfileComplete) {
        showToast('Please complete all required profile fields before applying', 'warning');
        window.location.hash = '#/profile';
        return;
      }

      const input = document.getElementById('job-url-input');
      const btn = document.getElementById('apply-btn');
      const url = input.value.trim();

      if (!url) {
        showToast('Please paste a job application URL', 'warning');
        return;
      }

      // LinkedIn check
      if (url.toLowerCase().includes('linkedin.com') && !_isLinkedInConnected) {
        showToast('Notice: LinkedIn session is not connected. If this is an Easy Apply job, connect in Settings first.', 'warning');
      }

      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-sm"></span> Submitting…';

      try {
        const data = await applicationsAPI.submit(url);
        showToast(`Application queued for ${data.application.company || 'the job'}!`, 'success');
        input.value = '';
        loadRateLimit();
        await loadRecentApps();
        startPolling();
      } catch (err) {
        showToast(err.message || 'Submission failed', 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '🚀 Apply';
      }
    });
  }

  async function checkLinkedInSession() {
    const pill = document.getElementById('linkedin-status-pill');
    if (!pill) return;

    try {
      const data = await linkedinAPI.status();
      _isLinkedInConnected = Boolean(data && data.connected);

      if (_isLinkedInConnected) {
        pill.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.2); border-radius: var(--radius-sm); font-size: 0.85rem;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="status-dot status-dot-green"></span>
              <span><strong>LinkedIn Session Active:</strong> Logged in as <em>${escapeHtml(data.user_name || 'Candidate')}</em></span>
            </div>
            <a href="#/settings" style="color: var(--accent); font-weight: 500; font-size: 0.82rem; text-decoration: none;">Manage Session →</a>
          </div>
        `;
      } else {
        pill.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: var(--radius-sm); font-size: 0.85rem;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="status-dot status-dot-gray"></span>
              <span><strong>LinkedIn Not Connected:</strong> Connect your session in Settings to enable 1-click Easy Apply.</span>
            </div>
            <a href="#/settings" class="btn btn-xs btn-primary" style="padding: 3px 10px; font-size: 0.8rem;">Connect LinkedIn →</a>
          </div>
        `;
      }
    } catch (err) {
      console.warn("Could not check LinkedIn session:", err);
    }
  }

  async function checkProfileCompleteness() {
    const banner = document.getElementById('profile-gate-banner');
    const input = document.getElementById('job-url-input');
    const btn = document.getElementById('apply-btn');
    if (!banner) return;

    try {
      const data = await profileAPI.completeness();
      _isProfileComplete = Boolean(data && data.is_complete);

      if (!_isProfileComplete) {
        if (input) {
          input.disabled = true;
          input.placeholder = "Profile must be 100% complete before applying";
        }
        if (btn) {
          btn.disabled = true;
          btn.title = "Complete profile to enable apply";
        }
        const missingLabels = (data.missing_fields || []).map(f => {
          const map = {
            name: 'Full Name',
            email: 'Email',
            phone: 'Phone',
            location: 'Location',
            education: 'Education',
            skills: 'Skills',
            notice_period: 'Notice Period',
            expected_ctc: 'Expected Compensation',
            work_authorization: 'Work Authorization'
          };
          return map[f] || f.replace(/_/g, ' ');
        }).join(', ');

        banner.innerHTML = `
          <div class="card" style="border: 1px solid var(--warning, #f59e0b); background: rgba(245, 158, 11, 0.08); margin-bottom: 20px; padding: 16px 20px;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
              <div>
                <h4 style="margin: 0 0 6px 0; color: var(--warning, #f59e0b); display: flex; align-items: center; gap: 8px;">
                  <span>⚠️</span> Profile Incomplete (${data.percent || 0}% Complete)
                </h4>
                <p style="margin: 0; font-size: 0.85rem; color: var(--text-secondary);">
                  Job applications are locked until your profile is 100% complete.
                  <strong>Missing:</strong> ${escapeHtml(missingLabels)}.
                </p>
              </div>
              <a href="#/profile" class="btn btn-primary btn-sm">Complete Profile →</a>
            </div>
          </div>
        `;
      } else {
        if (input) input.disabled = false;
        if (btn) btn.disabled = false;
        banner.innerHTML = `
          <div style="display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--success); margin-bottom: 16px; padding: 8px 12px; background: rgba(34, 197, 94, 0.08); border-radius: var(--radius-sm); border: 1px solid rgba(34, 197, 94, 0.2);">
            <span>✓</span> Profile is 100% complete. Automated 1-click apply is active!
          </div>
        `;
      }
    } catch (err) {
      console.warn("Could not check completeness:", err);
    }
  }

  async function loadRateLimit() {
    const bar = document.getElementById('rate-limit-bar');
    if (!bar) return;
    try {
      const data = await applicationsAPI.list({ per_page: 1 });
      const used = data.count_today || 0;
      const limit = data.limit || 50;
      const pct = Math.round((used / limit) * 100);
      const color = pct > 80 ? 'var(--error)' : pct > 50 ? 'var(--warning)' : 'var(--accent)';

      bar.innerHTML = `
        <div class="rate-limit-info">
          <span>${used} of ${limit} applications used today</span>
          <span class="text-muted">${limit - used} remaining</span>
        </div>
        <div class="progress-bar-track">
          <div class="progress-bar-fill" style="width: ${pct}%; background: ${color};"></div>
        </div>
      `;
    } catch (err) {
      bar.innerHTML = '<span class="text-muted">Could not load usage info</span>';
    }
  }

  async function loadRecentApps(isSilent = false) {
    const container = document.getElementById('recent-apps');
    if (!container) {
      stopPolling();
      return;
    }
    try {
      const data = await applicationsAPI.list({ per_page: 6 });
      const apps = data.applications || [];

      // Auto-poll if any app is QUEUED or APPLYING
      const hasActive = apps.some(a => a.status === 'QUEUED' || a.status === 'APPLYING');
      if (hasActive && !_pollInterval) {
        startPolling();
      } else if (!hasActive && _pollInterval) {
        stopPolling();
      }

      if (apps.length === 0) {
        container.innerHTML = '<p class="text-muted">No applications yet. Paste a URL above to get started!</p>';
        return;
      }

      let html = '<div class="recent-apps-list" style="display: flex; flex-direction: column; gap: 12px;">';
      for (const app of apps) {
        const statusClass = {
          QUEUED: 'badge-info',
          APPLYING: 'badge-warning',
          SUBMITTED: 'badge-warning',
          APPLIED: 'badge-success',
          FAILED: 'badge-error',
          NEEDS_ACTION: 'badge-orange',
        }[app.status] || 'badge-info';

        const statusLabel = app.status_display || {
          QUEUED: 'Pending',
          APPLYING: 'In Progress',
          SUBMITTED: 'Submitted – Unverified',
          APPLIED: 'Applied – Verified',
          FAILED: 'Failed',
          NEEDS_ACTION: 'Manual Intervention Required',
        }[app.status] || app.status;

        const date = new Date(app.created_at).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });

        const retryBtn = (app.status === 'FAILED' || app.status === 'NEEDS_ACTION')
          ? `<button class="btn btn-xs btn-warning retry-btn" data-id="${app.id}" style="padding: 2px 8px; font-size: 0.75rem;">Retry</button>`
          : '';

        // Check if awaiting review approval
        let approveBtn = '';
        if (app.status === 'NEEDS_ACTION' && app.action_details && app.action_details.type === 'review_approval') {
          approveBtn = `<button class="btn btn-xs btn-primary approve-btn" data-id="${app.id}" style="padding: 2px 10px; font-size: 0.75rem; background: var(--success); border-color: var(--success);">✓ Approve & Submit</button>`;
        }

        let alertBox = '';
        if (app.error_message) {
          const isAction = app.status === 'NEEDS_ACTION';
          const bg = isAction ? 'rgba(245, 158, 11, 0.08)' : 'rgba(239, 68, 68, 0.08)';
          const border = isAction ? 'var(--warning, #f59e0b)' : 'var(--error, #ef4444)';
          const icon = isAction ? '⚠️' : '❌';
          alertBox = `
            <div style="margin-top: 8px; padding: 8px 12px; background: ${bg}; border-left: 3px solid ${border}; border-radius: 4px; font-size: 0.82rem; line-height: 1.4;">
              <span style="font-weight: 600;">${icon} ${isAction ? 'Action Required' : 'Notice'}:</span> ${escapeHtml(app.error_message)}
            </div>
          `;
        }

        const resumeNote = app.resume_used ? `<span class="text-muted" style="font-size: 0.75rem;">• Resume: ${escapeHtml(app.resume_used)}</span>` : '';

        html += `
          <div class="recent-app-item" style="padding: 12px; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm);">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
              <div class="recent-app-info" style="display: flex; flex-direction: column; gap: 2px;">
                <span class="company" style="font-weight: 600; font-size: 0.95rem;">${escapeHtml(app.company || 'Job Application')}</span>
                <span class="role text-muted" style="font-size: 0.82rem;">${escapeHtml(app.role || app.url)} ${resumeNote}</span>
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="status-badge ${statusClass}">${statusLabel}</span>
                ${approveBtn}
                ${retryBtn}
                <span class="text-muted recent-app-date" style="font-size: 0.78rem;">${date}</span>
              </div>
            </div>
            ${alertBox}
          </div>
        `;
      }
      html += '</div>';
      container.innerHTML = html;

      // Bind retry buttons
      container.querySelectorAll('.retry-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.preventDefault();
          const appId = btn.dataset.id;
          btn.disabled = true;
          btn.textContent = 'Retrying…';
          try {
            await applicationsAPI.retry(appId);
            showToast('Application queued for retry!', 'info');
            loadRecentApps();
            startPolling();
          } catch (err) {
            showToast(err.message || 'Retry failed', 'error');
            btn.disabled = false;
            btn.textContent = 'Retry';
          }
        });
      });

      // Bind approve buttons
      container.querySelectorAll('.approve-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.preventDefault();
          const appId = btn.dataset.id;
          btn.disabled = true;
          btn.textContent = 'Submitting…';
          try {
            await applicationsAPI.approve(appId);
            showToast('Application approved! Submitting now 🚀', 'success');
            loadRecentApps();
            startPolling();
          } catch (err) {
            showToast(err.message || 'Approval failed', 'error');
            btn.disabled = false;
            btn.textContent = '✓ Approve & Submit';
          }
        });
      });

    } catch (err) {
      if (!isSilent) {
        container.innerHTML = `<p class="text-error">Failed to load: ${err.message}</p>`;
      }
    }
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  return { render };
})();
