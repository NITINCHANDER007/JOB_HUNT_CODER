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
      <div class="page-header" style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;">
        <div>
          <h1>Apply to a Job</h1>
          <p class="text-muted">Paste a job application link and AutoApply AI handles the rest</p>
        </div>
        <div id="rate-limit-badge" class="badge badge-info" style="font-size: 0.8rem; padding: 6px 12px; font-weight: 500;">
          <span class="spinner-sm"></span> Loading usage…
        </div>
      </div>

      <!-- Completeness Gate Banner (Only shown if profile is incomplete) -->
      <div id="profile-gate-banner"></div>

      <!-- LinkedIn Session Status Pill -->
      <div id="linkedin-status-pill" style="margin-bottom: 16px;"></div>

      <!-- Apply Form -->
      <div class="card apply-card" style="padding: 24px;">
        <form id="apply-form">
          <div class="apply-input-group">
            <input
              type="url"
              id="job-url-input"
              class="apply-input"
              placeholder="https://www.linkedin.com/jobs/view/... or Greenhouse, Lever, Ashby, ByteDance link"
              required
              autocomplete="url"
            />
            <button type="submit" class="btn btn-primary btn-lg" id="apply-btn">
              🚀 Apply
            </button>
          </div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; align-items: center;">
            <span class="text-muted" style="font-size: 0.78rem;">Supported:</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">LinkedIn Easy Apply</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">Greenhouse</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">Lever</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">Ashby</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">Workday</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">ByteDance</span>
            <span class="badge" style="background: rgba(255,255,255,0.06); font-size: 0.75rem;">Company Career Pages</span>
          </div>
        </form>
      </div>

      <!-- Recent Applications -->
      <div class="card" style="margin-top: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
          <h3 class="card-title" style="margin: 0;">Recent Submissions</h3>
          <a href="#/dashboard" class="text-muted text-xs" style="text-decoration: underline;">View All on Dashboard →</a>
        </div>
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
        banner.innerHTML = '';
      }
    } catch (err) {
      console.warn("Could not check completeness:", err);
    }
  }

  async function loadRateLimit() {
    const badge = document.getElementById('rate-limit-badge');
    if (!badge) return;
    try {
      const data = await applicationsAPI.list({ per_page: 1 });
      const used = data.count_today || 0;
      const limit = data.limit || 50;
      const remaining = Math.max(0, limit - used);
      badge.innerHTML = `⚡ <strong>${remaining}</strong> of ${limit} applies left today`;
    } catch (err) {
      badge.textContent = '50 applies / day';
    }
  }

  async function loadRecentApps(isSilent = false) {
    const container = document.getElementById('recent-apps');
    if (!container) {
      stopPolling();
      return;
    }
    try {
      const data = await applicationsAPI.list({ per_page: 4 });
      const apps = data.applications || [];

      // Auto-poll if any app is QUEUED or APPLYING
      const hasActive = apps.some(a => a.status === 'QUEUED' || a.status === 'APPLYING');
      if (hasActive && !_pollInterval) {
        startPolling();
      } else if (!hasActive && _pollInterval) {
        stopPolling();
      }

      if (apps.length === 0) {
        container.innerHTML = '<p class="text-muted text-sm" style="margin: 4px 0;">No applications submitted yet. Paste a URL above to start.</p>';
        return;
      }

      let html = '<div class="recent-apps-list" style="display: flex; flex-direction: column; gap: 8px;">';
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
          NEEDS_ACTION: 'Action Required',
        }[app.status] || app.status;

        const date = new Date(app.created_at).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });

        const retryBtn = (app.status === 'FAILED' || app.status === 'NEEDS_ACTION')
          ? `<button class="btn btn-xs btn-warning retry-btn" data-id="${app.id}" style="padding: 2px 8px; font-size: 0.75rem;">Retry</button>`
          : '';

        let approveBtn = '';
        if (app.status === 'NEEDS_ACTION' && app.action_details && app.action_details.type === 'review_approval') {
          approveBtn = `<button class="btn btn-xs btn-primary approve-btn" data-id="${app.id}" style="padding: 2px 10px; font-size: 0.75rem; background: var(--success); border-color: var(--success);">✓ Approve</button>`;
        }

        const errorTooltip = app.error_message
          ? `<span class="text-muted" style="cursor: help; font-size: 0.78rem;" title="${escapeAttr(app.error_message)}">ⓘ Info</span>`
          : '';

        html += `
          <div class="recent-app-item" style="padding: 10px 14px; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
            <div class="recent-app-info" style="display: flex; flex-direction: column; gap: 2px; min-width: 200px;">
              <span class="company" style="font-weight: 600; font-size: 0.9rem;">${escapeHtml(app.company || 'Job Application')}</span>
              <span class="role text-muted" style="font-size: 0.78rem;">${escapeHtml(app.role || app.url)}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              ${errorTooltip}
              <span class="status-badge ${statusClass}">${statusLabel}</span>
              ${approveBtn}
              ${retryBtn}
              <span class="text-muted recent-app-date" style="font-size: 0.75rem;">${date}</span>
            </div>
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
