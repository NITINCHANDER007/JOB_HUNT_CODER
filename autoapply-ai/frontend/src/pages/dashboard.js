/**
 * AutoApply AI — Dashboard Page
 * Shows stats cards, applications table with 6 lifecycle statuses,
 * resume used tracking, review approval, and confirmation evidence.
 */

const DashboardPage = (() => {
  let _refreshInterval = null;

  async function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1>Dashboard</h1>
        <p class="text-muted">Track and verify your job applications across all platforms</p>
      </div>

      <!-- Stats Cards -->
      <div class="stats-grid" id="stats-grid">
        <div class="stat-card"><div class="spinner-sm"></div></div>
      </div>

      <!-- Filter Bar with 6 Canonical Statuses -->
      <div class="filter-bar" id="filter-bar" style="overflow-x: auto; padding-bottom: 6px;">
        <button class="filter-btn active" data-status="">All</button>
        <button class="filter-btn" data-status="QUEUED">Pending</button>
        <button class="filter-btn" data-status="APPLYING">In Progress</button>
        <button class="filter-btn" data-status="SUBMITTED">Submitted – Unverified</button>
        <button class="filter-btn" data-status="APPLIED">Applied – Verified</button>
        <button class="filter-btn" data-status="NEEDS_ACTION">Action Required</button>
        <button class="filter-btn" data-status="FAILED">Failed</button>
      </div>

      <!-- Applications Table -->
      <div class="table-container" id="applications-table-container">
        <div class="page-loading"><div class="spinner"></div></div>
      </div>

      <!-- Pagination -->
      <div class="pagination" id="pagination"></div>
    `;

    // Load data
    await Promise.all([loadStats(), loadApplications('')]);

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadApplications(btn.dataset.status);
      });
    });

    // Auto-refresh every 25 seconds
    if (_refreshInterval) clearInterval(_refreshInterval);
    _refreshInterval = setInterval(() => {
      const activeFilter = document.querySelector('.filter-btn.active');
      const status = activeFilter ? activeFilter.dataset.status : '';
      loadStats();
      loadApplications(status);
    }, 25000);
  }

  async function loadStats() {
    try {
      const stats = await dashboardAPI.stats();
      const grid = document.getElementById('stats-grid');
      if (!grid) return;

      grid.innerHTML = `
        <div class="stat-card">
          <div class="stat-value">${stats.total_applications}</div>
          <div class="stat-label">Total Applications</div>
        </div>
        <div class="stat-card stat-success">
          <div class="stat-value">${stats.applied_count}</div>
          <div class="stat-label">Applied – Verified</div>
        </div>
        <div class="stat-card stat-warning">
          <div class="stat-value">${stats.queued_count}</div>
          <div class="stat-label">In Progress / Pending</div>
        </div>
        <div class="stat-card stat-error">
          <div class="stat-value">${(stats.failed_count || 0) + (stats.needs_action_count || 0)}</div>
          <div class="stat-label">Action / Failed</div>
        </div>
        <div class="stat-card stat-info">
          <div class="stat-value">${stats.success_rate}%</div>
          <div class="stat-label">Success Rate</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${stats.applications_this_week}</div>
          <div class="stat-label">This Week</div>
        </div>
      `;
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }

  async function loadApplications(status) {
    const tableContainer = document.getElementById('applications-table-container');
    if (!tableContainer) return;

    try {
      const params = {};
      if (status) params.status = status;

      const data = await applicationsAPI.list(params);
      const apps = data.applications || [];

      if (apps.length === 0) {
        tableContainer.innerHTML = `
          <div class="empty-state">
            <span class="empty-icon">📋</span>
            <h3>No applications found</h3>
            <p>Go to the <a href="#/apply">Apply</a> page to submit your first job application.</p>
          </div>
        `;
        return;
      }

      let rows = '';
      for (const app of apps) {
        const statusClass = getStatusClass(app.status);
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
        const company = app.company || 'Unknown';
        const role = app.role || 'Unknown';
        const resumeUsed = app.resume_used ? `<div style="font-size: 0.75rem; color: var(--text-secondary);">📄 ${escapeHtml(app.resume_used)}</div>` : '';
        const errorInfo = app.error_message ? `<span class="error-hint" title="${escapeAttr(app.error_message)}" style="cursor: help; margin-left: 4px;">ⓘ</span>` : '';

        const confirmLink = app.confirmation_url
          ? `<a href="${app.confirmation_url}" target="_blank" class="confirm-link">Receipt ↗</a>`
          : (app.confirmation_email ? `<span class="confirm-email" title="${escapeAttr(app.confirmation_email.subject || '')}">📧 Confirmed</span>` : '—');

        const retryBtn = (app.status === 'FAILED' || app.status === 'NEEDS_ACTION')
          ? `<button class="btn btn-xs btn-warning retry-btn" data-id="${app.id}">Retry</button>`
          : '';

        let approveBtn = '';
        if (app.status === 'NEEDS_ACTION' && app.action_details && app.action_details.type === 'review_approval') {
          approveBtn = `<button class="btn btn-xs btn-primary approve-btn" data-id="${app.id}" style="background: var(--success); border-color: var(--success);" title="Approve & Submit">✓ Approve</button>`;
        }

        const screenshotBtn = app.screenshot_path
          ? `<button class="btn btn-xs btn-ghost screenshot-btn" data-id="${app.id}" title="View Screenshot">📸</button>`
          : '';
        const deleteBtn = `<button class="btn btn-xs btn-ghost delete-btn" data-id="${app.id}" title="Delete">🗑</button>`;

        rows += `
          <tr>
            <td class="cell-company">
              <div class="company-name" style="font-weight: 600;">${escapeHtml(company)}</div>
              <div class="role-name text-muted" style="font-size: 0.82rem;">${escapeHtml(role)}</div>
              ${resumeUsed}
            </td>
            <td><span class="status-badge ${statusClass}">${statusLabel}${errorInfo}</span></td>
            <td class="cell-date">${date}</td>
            <td class="cell-confirm">${confirmLink}</td>
            <td class="cell-actions">${approveBtn} ${retryBtn} ${screenshotBtn} ${deleteBtn}</td>
          </tr>
        `;
      }

      tableContainer.innerHTML = `
        <table class="app-table">
          <thead>
            <tr>
              <th>Company & Role</th>
              <th>Status</th>
              <th>Submitted</th>
              <th>Evidence / Receipt</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;

      // Bind action buttons
      tableContainer.querySelectorAll('.retry-btn').forEach(btn => {
        btn.addEventListener('click', () => retryApp(btn.dataset.id));
      });
      tableContainer.querySelectorAll('.approve-btn').forEach(btn => {
        btn.addEventListener('click', () => approveApp(btn.dataset.id));
      });
      tableContainer.querySelectorAll('.screenshot-btn').forEach(btn => {
        btn.addEventListener('click', () => viewScreenshot(btn.dataset.id));
      });
      tableContainer.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', () => deleteApp(btn.dataset.id));
      });

      // Pagination
      const pagination = document.getElementById('pagination');
      if (pagination && data.pagination) {
        const p = data.pagination;
        let paginationHtml = '';
        if (p.has_prev) {
          paginationHtml += `<button class="btn btn-sm btn-ghost" onclick="DashboardPage._loadPage(${p.page - 1}, '${status}')">← Prev</button>`;
        }
        paginationHtml += `<span class="pagination-info">Page ${p.page} of ${p.pages} (${p.total} total)</span>`;
        if (p.has_next) {
          paginationHtml += `<button class="btn btn-sm btn-ghost" onclick="DashboardPage._loadPage(${p.page + 1}, '${status}')">Next →</button>`;
        }
        pagination.innerHTML = paginationHtml;
      }

    } catch (err) {
      tableContainer.innerHTML = `<p class="text-error">Failed to load applications: ${err.message}</p>`;
    }
  }

  async function approveApp(id) {
    try {
      await applicationsAPI.approve(id);
      showToast('Application approved! Submitting now 🚀', 'success');
      loadApplications('');
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function retryApp(id) {
    try {
      await applicationsAPI.retry(id);
      showToast('Application queued for retry', 'success');
      loadApplications('');
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function viewScreenshot(id) {
    const url = applicationsAPI.screenshotUrl(id);
    openGlobalModal(`
      <div class="screenshot-modal">
        <h3>Application Submission Screenshot</h3>
        <img src="${url}" alt="Screenshot"
             style="max-width:100%; border-radius:8px; margin-top:12px; border: 1px solid var(--border);"
             onerror="this.alt='Screenshot not available on disk'; this.style.display='none';" />
      </div>
    `);
  }

  async function deleteApp(id) {
    if (!confirm('Delete this application record?')) return;
    try {
      await applicationsAPI.delete(id);
      showToast('Application deleted', 'info');
      loadApplications('');
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function getStatusClass(status) {
    const map = {
      QUEUED: 'badge-info',
      APPLYING: 'badge-warning',
      SUBMITTED: 'badge-warning',
      APPLIED: 'badge-success',
      FAILED: 'badge-error',
      NEEDS_ACTION: 'badge-orange',
    };
    return map[status] || 'badge-info';
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }
  function escapeAttr(str) {
    return (str || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  return {
    render,
    _loadPage: (page, status) => {
      loadApplications(status);
    }
  };
})();
