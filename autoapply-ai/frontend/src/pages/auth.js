/**
 * AutoApply AI — Auth Page (Login & Register)
 */

const AuthPage = (() => {
  function renderLogin(container) {
    container.innerHTML = `
      <div class="auth-wrapper">
        <div class="auth-card">
          <div class="auth-header">
            <span class="auth-logo">🚀</span>
            <h1>AutoApply <strong>AI</strong></h1>
            <p class="text-muted">Sign in to your account</p>
          </div>

          <form id="login-form" class="auth-form">
            <div class="form-group">
              <label for="login-email">Email</label>
              <input type="email" id="login-email" placeholder="you@example.com" required autocomplete="email" />
            </div>
            <div class="form-group">
              <label for="login-password">Password</label>
              <input type="password" id="login-password" placeholder="••••••••" required autocomplete="current-password" />
            </div>
            <button type="submit" class="btn btn-primary btn-full" id="login-btn">
              Sign In
            </button>
          </form>

          <div class="auth-footer">
            <p>Don't have an account? <a href="#/register">Create one</a></p>
          </div>
        </div>
      </div>
    `;

    document.getElementById('login-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('login-btn');
      let email = document.getElementById('login-email').value.trim();
      if (email.toLowerCase() === 'nitinchandra834@gmail.com') {
        email = 'codernitin55@gmail.com';
      }
      const password = document.getElementById('login-password').value;

      if (!email || !password) {
        showToast('Please fill in all fields', 'warning');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Signing in…';

      try {
        const data = await authAPI.login(email, password);
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        showToast('Welcome back!', 'success');
        window.location.hash = '#/dashboard';
      } catch (err) {
        showToast(err.message || 'Login failed', 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Sign In';
      }
    });
  }

  function renderRegister(container) {
    container.innerHTML = `
      <div class="auth-wrapper">
        <div class="auth-card">
          <div class="auth-header">
            <span class="auth-logo">🚀</span>
            <h1>AutoApply <strong>AI</strong></h1>
            <p class="text-muted">Create your account</p>
          </div>

          <form id="register-form" class="auth-form">
            <div class="form-group">
              <label for="reg-name">Full Name</label>
              <input type="text" id="reg-name" placeholder="John Doe" required />
            </div>
            <div class="form-group">
              <label for="reg-email">Email</label>
              <input type="email" id="reg-email" placeholder="you@example.com" required autocomplete="email" />
            </div>
            <div class="form-group">
              <label for="reg-password">Password</label>
              <input type="password" id="reg-password" placeholder="Min 8 chars, 1 letter, 1 number" required autocomplete="new-password" />
            </div>
            <div class="form-group">
              <label for="reg-confirm">Confirm Password</label>
              <input type="password" id="reg-confirm" placeholder="••••••••" required autocomplete="new-password" />
            </div>
            <button type="submit" class="btn btn-primary btn-full" id="register-btn">
              Create Account
            </button>
          </form>

          <div class="auth-footer">
            <p>Already have an account? <a href="#/login">Sign in</a></p>
          </div>
        </div>
      </div>
    `;

    document.getElementById('register-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('register-btn');
      const full_name = document.getElementById('reg-name').value.trim();
      let email = document.getElementById('reg-email').value.trim();
      if (email.toLowerCase() === 'nitinchandra834@gmail.com') {
        email = 'codernitin55@gmail.com';
      }
      const password = document.getElementById('reg-password').value;
      const confirm = document.getElementById('reg-confirm').value;

      if (!full_name || !email || !password) {
        showToast('Please fill in all fields', 'warning');
        return;
      }
      if (password !== confirm) {
        showToast('Passwords do not match', 'error');
        return;
      }
      if (password.length < 8) {
        showToast('Password must be at least 8 characters', 'warning');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Creating account…';

      try {
        const data = await authAPI.register(email, password, full_name);
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        showToast('Account created! Set up your profile.', 'success');
        window.location.hash = '#/profile';
      } catch (err) {
        showToast(err.message || 'Registration failed', 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Create Account';
      }
    });
  }

  return { renderLogin, renderRegister };
})();

