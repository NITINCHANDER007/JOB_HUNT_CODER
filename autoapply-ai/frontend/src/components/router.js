/**
 * AutoApply AI — Hash-based SPA Router
 * Maps hash routes to page render functions and handles auth redirects.
 */

const Router = (() => {
  // Route registry: hash path -> { render, requiresAuth, title }
  const routes = {
    '/login':     { render: AuthPage.renderLogin,    requiresAuth: false, title: 'Login' },
    '/register':  { render: AuthPage.renderRegister, requiresAuth: false, title: 'Register' },
    '/dashboard': { render: DashboardPage.render,    requiresAuth: true,  title: 'Dashboard' },
    '/apply':     { render: ApplyPage.render,        requiresAuth: true,  title: 'Apply' },
    '/profile':   { render: ProfilePage.render,      requiresAuth: true,  title: 'Profile' },
    '/settings':  { render: SettingsPage.render,     requiresAuth: true,  title: 'Settings' },
  };

  function isAuthenticated() {
    return !!localStorage.getItem('token');
  }

  function navigate(hash) {
    window.location.hash = hash;
  }

  function getCurrentRoute() {
    const hash = window.location.hash.replace('#', '') || '/dashboard';
    return hash;
  }

  function updateActiveNav(route) {
    const navLinks = document.querySelectorAll('#sidebar-nav .nav-link');
    navLinks.forEach(link => {
      const linkRoute = link.getAttribute('data-route');
      if (linkRoute === route) {
        link.classList.add('active');
      } else {
        link.classList.remove('active');
      }
    });
  }

  function showAppShell(visible) {
    const sidebar = document.getElementById('sidebar');
    const topbar = document.getElementById('topbar');
    if (sidebar) sidebar.style.display = visible ? '' : 'none';
    if (topbar) topbar.style.display = visible ? '' : 'none';

    const mainWrapper = document.getElementById('main-wrapper');
    if (mainWrapper) {
      mainWrapper.style.marginLeft = visible ? '' : '0';
    }
  }

  async function handleRoute() {
    const route = getCurrentRoute();
    const routeConfig = routes[route];
    const mainContent = document.getElementById('main-content');

    if (!routeConfig) {
      // Default redirect
      if (isAuthenticated()) {
        navigate('#/dashboard');
      } else {
        navigate('#/login');
      }
      return;
    }

    // Auth check
    if (routeConfig.requiresAuth && !isAuthenticated()) {
      navigate('#/login');
      return;
    }

    // If authenticated and trying to access login/register, redirect to dashboard
    if (!routeConfig.requiresAuth && isAuthenticated() && (route === '/login' || route === '/register')) {
      navigate('#/dashboard');
      return;
    }

    // Show/hide app shell (hide for login/register)
    showAppShell(routeConfig.requiresAuth);

    // Update page title
    document.title = `${routeConfig.title} — AutoApply AI`;

    // Update nav highlights
    updateActiveNav(route);

    // Close mobile sidebar
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');

    // Show loading spinner
    mainContent.innerHTML = `
      <div class="page-loading">
        <div class="spinner"></div>
        <p>Loading…</p>
      </div>
    `;

    // Render the page
    try {
      await routeConfig.render(mainContent);
    } catch (err) {
      console.error('Page render error:', err);
      mainContent.innerHTML = `
        <div class="error-page">
          <h2>Something went wrong</h2>
          <p>${err.message}</p>
          <button class="btn btn-primary" onclick="location.reload()">Reload</button>
        </div>
      `;
    }
  }

  // Initialize
  function init() {
    window.addEventListener('hashchange', handleRoute);
    // Initial route
    if (!window.location.hash) {
      window.location.hash = isAuthenticated() ? '#/dashboard' : '#/login';
    } else {
      handleRoute();
    }
  }

  // Start router on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { navigate, getCurrentRoute, isAuthenticated };
})();

