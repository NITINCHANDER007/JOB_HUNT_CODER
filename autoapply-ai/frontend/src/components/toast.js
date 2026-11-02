/**
 * AutoApply AI — Toast Notification System
 * Displays slide-in notifications. Supports: info, success, error, warning.
 */

const Toast = (() => {
  let _counter = 0;

  function show(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    _counter++;
    const id = `toast-${_counter}`;

    const iconMap = {
      info:    'ℹ️',
      success: '✅',
      error:   '❌',
      warning: '⚠️',
    };

    const toast = document.createElement('div');
    toast.id = id;
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${iconMap[type] || 'ℹ️'}</span>
      <span class="toast-message">${_escapeHtml(message)}</span>
      <button class="toast-close" onclick="Toast.dismiss('${id}')">&times;</button>
    `;

    container.appendChild(toast);

    // Trigger slide-in animation
    requestAnimationFrame(() => toast.classList.add('toast-show'));

    // Auto-dismiss
    if (duration > 0) {
      setTimeout(() => Toast.dismiss(id), duration);
    }
  }

  function dismiss(id) {
    const toast = document.getElementById(id);
    if (!toast) return;
    toast.classList.remove('toast-show');
    toast.classList.add('toast-hide');
    setTimeout(() => toast.remove(), 300);
  }

  function _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  return { show, dismiss };
})();

/* Convenience helpers */
function showToast(message, type = 'info', duration = 4000) {
  Toast.show(message, type, duration);
}

