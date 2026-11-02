/**
 * AutoApply AI — API Client
 * Centralized API calls with JWT auth header injection.
 */

const BASE_URL = (window.location.origin && window.location.origin.startsWith('http') && !window.location.origin.includes(':3000'))
  ? window.location.origin
  : 'http://localhost:5050';

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function _request(method, path, body = null, isFormData = false) {
  const token = localStorage.getItem('token');
  const headers = {};

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (body && !isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  const opts = {
    method,
    headers,
    body: body
      ? (isFormData ? body : JSON.stringify(body))
      : undefined,
  };

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, opts);
  } catch (err) {
    throw new Error('Network error: ' + err.message);
  }

  // Handle 401 — redirect to login
  if (response.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.hash = '#/login';
    throw new Error('Session expired. Please log in again.');
  }

  // Parse JSON (best-effort)
  let data;
  const ct = response.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const msg =
      (typeof data === 'object' && (data.error || data.message)) ||
      `HTTP ${response.status}`;
    throw new Error(msg);
  }

  return data;
}

const api = {
  get: (path) => _request('GET', path),
  post: (path, body) => _request('POST', path, body),
  put: (path, body) => _request('PUT', path, body),
  patch: (path, body) => _request('PATCH', path, body),
  delete: (path) => _request('DELETE', path),
  upload: (path, formData) => _request('POST', path, formData, true),
};

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

const authAPI = {
  login: (email, password) => api.post('/api/auth/login', { email, password }),
  register: (email, password, full_name) => api.post('/api/auth/register', { email, password, full_name }),
  me: () => api.get('/api/auth/me'),
  changePassword: (current, newPass) => api.post('/api/auth/change-password', {
    current_password: current,
    new_password: newPass,
  }),
  deleteAccount: () => api.delete('/api/auth/account'),
};

// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

const applicationsAPI = {
  submit: (url) => api.post('/api/applications/', { url }),
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return api.get(`/api/applications/${q ? '?' + q : ''}`);
  },
  get: (id) => api.get(`/api/applications/${id}`),
  delete: (id) => api.delete(`/api/applications/${id}`),
  retry: (id) => api.post(`/api/applications/${id}/retry`),
  approve: (id) => api.post(`/api/applications/${id}/approve`),
  screenshotUrl: (id) => `${BASE_URL}/api/applications/${id}/screenshot`,
  checkEmbeddable: (url) => api.get(`/api/applications/check-embeddable?url=${encodeURIComponent(url)}`),
};

// ---------------------------------------------------------------------------
// LinkedIn Session & Browser Automation API
// ---------------------------------------------------------------------------

const linkedinAPI = {
  status: () => api.get('/api/linkedin/session/status'),
  connect: () => api.post('/api/linkedin/session/connect'),
  connectStatus: () => api.get('/api/linkedin/session/connect-status'),
  verify: () => api.post('/api/linkedin/session/verify'),
  disconnect: () => api.post('/api/linkedin/session/disconnect'),
  updateSettings: (data) => api.post('/api/linkedin/settings', data),
};

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

const dashboardAPI = {
  stats: () => api.get('/api/dashboard/stats'),
  feed: () => api.get('/api/dashboard/feed'),
};

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

const profileAPI = {
  get: () => api.get('/api/profile'),
  update: (data) => api.put('/api/profile', data),
  completeness: () => api.get('/api/profile/completeness'),
  complete: (data) => api.put('/api/profile/complete', data),
  uploadResume: (file) => {
    const fd = new FormData();
    fd.append('resume', file);
    return api.upload('/api/profile/resume', fd);
  },
  deleteResume: (id) => api.delete(`/api/profile/resume/${id}`),
  setPrimaryResume: (id) => api.post(`/api/profile/resume/${id}/primary`),
  listResumes: () => api.get('/api/profile/resumes'),
};

// ---------------------------------------------------------------------------
// Resume Parsing API
// ---------------------------------------------------------------------------

const resumeAPI = {
  upload: (file, forceOverwrite = false) => {
    const fd = new FormData();
    fd.append('resume', file);
    if (forceOverwrite) {
      fd.append('force_overwrite', 'true');
    }
    return api.upload('/api/resume/upload', fd);
  },
};

// ---------------------------------------------------------------------------
// Gmail
// ---------------------------------------------------------------------------

const gmailAPI = {
  authUrl: () => api.get('/api/gmail/auth'),
  disconnect: () => api.delete('/api/gmail/disconnect'),
  status: () => api.get('/api/gmail/status'),
  sync: () => api.post('/api/gmail/sync'),
};

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

const settingsAPI = {
  getRateLimitInfo: () => api.get('/api/applications/?per_page=1'),
};

// ---------------------------------------------------------------------------
// Chatbot / Co-Pilot API
// ---------------------------------------------------------------------------

const chatAPI = {
  status: () => api.get('/api/chat/status'),
  answer: (appId, fieldKey, answer, saveToProfile = true) => api.post('/api/chat/answer', {
    application_id: appId,
    field_key: fieldKey,
    answer: answer,
    save_to_profile: saveToProfile,
  }),
  resume: (appId) => api.post('/api/chat/resume', { application_id: appId }),
  retry: (appId) => api.post(`/api/applications/${appId}/retry`),
  checkEmbeddable: (url) => api.get(`/api/applications/check-embeddable?url=${encodeURIComponent(url)}`),
  sendMessage: (message) => api.post('/api/chat/message', { message }),
};
