/**
 * AutoApply AI — Profile Page
 * Smart Profile Completion, AI Resume Parsing (PDF/DOCX),
 * Live Completeness Tracking, and Re-upload Diff Reconciliation.
 */

const ProfilePage = (() => {
  let _profile = {};
  let _user = {};
  let _resumes = [];
  let _pendingDiff = null;

  const REQUIRED_FIELD_KEYS = [
    { key: 'name', label: 'Full Name', selector: '#p-name' },
    { key: 'email', label: 'Email Address', selector: '#p-email' },
    { key: 'phone', label: 'Phone Number', selector: '#p-phone' },
    { key: 'location', label: 'Location', selector: '#p-location' },
    { key: 'notice_period', label: 'Notice Period', selector: '#p-notice' },
    { key: 'expected_ctc', label: 'Expected Compensation', selector: '#p-expected-ctc' },
    { key: 'work_authorization', label: 'Work Authorization', selector: '#p-work-auth' },
    { key: 'skills', label: 'Skills', selector: '#p-skills' },
    { key: 'education', label: 'Education', selector: '#education-list' },
  ];

  async function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1>Profile & Resume</h1>
        <p class="text-muted">Manage your profile details and upload resumes for AI-powered auto-applications</p>
      </div>

      <!-- Completeness Progress Bar -->
      <div class="profile-completeness-banner" id="completeness-banner">
        <div class="completeness-header">
          <div class="completeness-title">
            <span>⚡ Profile Completeness:</span>
            <span id="completeness-pct-text" class="completeness-pct incomplete">0%</span>
            <span id="completeness-badge" class="badge badge-warning">Incomplete</span>
          </div>
          <div class="text-muted text-sm" id="completeness-summary">
            Checking required fields…
          </div>
        </div>
        <div class="completeness-bar-track">
          <div id="completeness-bar-fill" class="completeness-bar-fill incomplete" style="width: 0%;"></div>
        </div>
        <div id="missing-tags-container" class="missing-fields-tags"></div>
      </div>

      <!-- Resume Upload Card -->
      <div class="card" style="margin-bottom: 24px;">
        <h3 class="card-title">📄 Smart Resume Parser</h3>
        <p class="text-muted text-sm" style="margin-bottom: 16px;">
          Upload your resume in PDF or DOCX format. Gemini AI will automatically extract your contact info,
          work experience, education, projects, and skills to pre-fill your profile.
        </p>

        <div class="resume-upload-area" id="resume-upload-area">
          <input type="file" id="resume-file-input" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" style="display:none" />
          <div class="upload-dropzone" id="upload-dropzone" style="cursor: pointer; padding: 28px 20px; border: 2px dashed var(--border); border-radius: var(--radius-lg); text-align: center; transition: all 0.2s;">
            <div id="upload-dropzone-content">
              <span class="upload-icon" style="font-size: 2.2rem; display: block; margin-bottom: 8px;">📂</span>
              <p style="margin: 0; font-weight: 600;">Drag & drop your resume (PDF or DOCX) here, or <span style="color: var(--accent); text-decoration: underline;">click to browse</span></p>
              <p class="text-muted text-xs" style="margin-top: 6px;">Supported formats: PDF, DOCX • Maximum file size: 5 MB</p>
            </div>
            <div id="upload-dropzone-loading" style="display: none; padding: 12px;">
              <div class="spinner-sm" style="display: inline-block; vertical-align: middle; margin-right: 8px;"></div>
              <span style="font-weight: 600;">Extracting text & parsing with Gemini AI… Please wait…</span>
            </div>
          </div>
        </div>

        <div id="resume-list" style="margin-top: 20px;"></div>
      </div>

      <!-- Main Profile Form -->
      <form id="profile-form" class="profile-form">

        <!-- Personal Info -->
        <div class="card" id="card-personal-info">
          <h3 class="card-title">Personal Information</h3>
          <div class="form-grid">
            <div class="form-group" id="group-p-name">
              <label for="p-name">Full Name <span class="badge-required">Required</span></label>
              <input type="text" id="p-name" placeholder="John Doe" required />
            </div>
            <div class="form-group" id="group-p-email">
              <label for="p-email">Email Address <span class="badge-required">Required</span></label>
              <input type="email" id="p-email" placeholder="john@example.com" required />
            </div>
            <div class="form-group" id="group-p-phone">
              <label for="p-phone">Phone Number <span class="badge-required">Required</span></label>
              <input type="tel" id="p-phone" placeholder="+1 (555) 000-0000" required />
            </div>
            <div class="form-group" id="group-p-location">
              <label for="p-location">Location (City, Country) <span class="badge-required">Required</span></label>
              <input type="text" id="p-location" placeholder="San Francisco, CA, USA" required />
            </div>
            <div class="form-group">
              <label for="p-linkedin">LinkedIn URL</label>
              <input type="url" id="p-linkedin" placeholder="https://linkedin.com/in/yourname" />
            </div>
            <div class="form-group">
              <label for="p-github">GitHub URL</label>
              <input type="url" id="p-github" placeholder="https://github.com/yourname" />
            </div>
            <div class="form-group">
              <label for="p-portfolio">Portfolio / Personal Site</label>
              <input type="url" id="p-portfolio" placeholder="https://yoursite.com" />
            </div>
            <div class="form-group">
              <label for="p-pronouns">Pronouns</label>
              <input type="text" id="p-pronouns" placeholder="he/him, she/her, they/them" />
            </div>
          </div>
        </div>

        <!-- Professional Info -->
        <div class="card" id="card-professional-info">
          <h3 class="card-title">Professional & Work Authorization</h3>
          <div class="form-grid">
            <div class="form-group">
              <label for="p-title">Current / Target Title</label>
              <input type="text" id="p-title" placeholder="Senior Full-Stack Engineer" />
            </div>
            <div class="form-group">
              <label for="p-yoe">Years of Experience</label>
              <input type="number" id="p-yoe" min="0" max="50" placeholder="5" />
            </div>
            <div class="form-group" id="group-p-notice">
              <label for="p-notice">Notice Period <span class="badge-required">Required</span></label>
              <input type="text" id="p-notice" placeholder="Immediate, 2 weeks, 1 month, etc." required />
            </div>
            <div class="form-group" id="group-p-expected-ctc">
              <label for="p-expected-ctc">Expected Compensation <span class="badge-required">Required</span></label>
              <input type="text" id="p-expected-ctc" placeholder="$120,000 USD / year" required />
            </div>
            <div class="form-group">
              <label for="p-current-ctc">Current Compensation</label>
              <input type="text" id="p-current-ctc" placeholder="$100,000 USD / year" />
            </div>
            <div class="form-group" id="group-p-work-auth">
              <label for="p-work-auth">Work Authorization <span class="badge-required">Required</span></label>
              <select id="p-work-auth" required>
                <option value="">Select authorization status…</option>
                <option value="US Citizen">US Citizen</option>
                <option value="Permanent Resident / Green Card">Permanent Resident / Green Card</option>
                <option value="H1B Visa">H1B Visa</option>
                <option value="OPT / CPT">OPT / CPT</option>
                <option value="Authorized to work in US">Authorized to work in US</option>
                <option value="Authorized to work in India">Authorized to work in India</option>
                <option value="UK Citizen / ILR">UK Citizen / ILR</option>
                <option value="EU Citizen / Work Permit">EU Citizen / Work Permit</option>
                <option value="Canadian Citizen / PR">Canadian Citizen / PR</option>
                <option value="Need Visa Sponsorship">Need Visa Sponsorship</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div class="form-group">
              <label for="p-remote">Remote Preference</label>
              <select id="p-remote">
                <option value="">Select…</option>
                <option value="Remote">Remote</option>
                <option value="Hybrid">Hybrid</option>
                <option value="Onsite">Onsite</option>
                <option value="Flexible">Flexible</option>
              </select>
            </div>
            <div class="form-group">
              <label for="p-relocate">Willing to Relocate</label>
              <select id="p-relocate">
                <option value="">Select…</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>
          </div>
          <div class="form-group" style="margin-top: 16px;">
            <label for="p-summary">Professional Summary</label>
            <textarea id="p-summary" rows="3" placeholder="Brief professional overview tailored for applications…"></textarea>
          </div>
        </div>

        <!-- Skills -->
        <div class="card" id="card-skills">
          <h3 class="card-title">Skills <span class="badge-required">Required</span></h3>
          <div class="form-group" id="group-p-skills">
            <label for="p-skills">Skills (comma-separated list)</label>
            <textarea id="p-skills" rows="3" placeholder="Python, JavaScript, React, Flask, PostgreSQL, Docker, AWS, Celery, Redis…" required></textarea>
            <p class="text-muted text-xs" style="margin-top: 4px;">These skills are dynamically matched against job descriptions when applying.</p>
          </div>
        </div>

        <!-- Education -->
        <div class="card" id="card-education">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <h3 class="card-title" style="margin: 0;">Education <span class="badge-required">Required</span></h3>
            <button type="button" class="btn btn-ghost btn-sm" id="add-education-btn">+ Add Education</button>
          </div>
          <p class="text-muted text-xs" style="margin-bottom: 14px;">At least one education entry is required for automated applications.</p>
          <div id="education-list"></div>
        </div>

        <!-- Experience -->
        <div class="card" id="card-experience">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <h3 class="card-title" style="margin: 0;">Work Experience</h3>
            <button type="button" class="btn btn-ghost btn-sm" id="add-experience-btn">+ Add Experience</button>
          </div>
          <div id="experience-list"></div>
        </div>

        <!-- EEO (collapsible) -->
        <div class="card">
          <h3 class="card-title collapsible" id="eeo-toggle" style="cursor:pointer">
            EEO / Voluntary Demographic Information (Optional) <span id="eeo-arrow">▸</span>
          </h3>
          <div id="eeo-section" style="display:none">
            <p class="text-muted text-sm" style="margin-bottom:16px;">
              Used exclusively to answer voluntary Equal Employment Opportunity questions when requested by companies.
            </p>
            <div class="form-grid">
              <div class="form-group">
                <label for="p-gender">Gender</label>
                <select id="p-gender">
                  <option value="">Prefer not to answer</option>
                  <option>Male</option>
                  <option>Female</option>
                  <option>Non-binary</option>
                  <option>Other</option>
                </select>
              </div>
              <div class="form-group">
                <label for="p-ethnicity">Race / Ethnicity</label>
                <select id="p-ethnicity">
                  <option value="">Prefer not to answer</option>
                  <option>Hispanic or Latino</option>
                  <option>White (Not Hispanic or Latino)</option>
                  <option>Black or African American</option>
                  <option>Asian</option>
                  <option>American Indian or Alaska Native</option>
                  <option>Two or More Races</option>
                </select>
              </div>
              <div class="form-group">
                <label for="p-veteran">Veteran Status</label>
                <select id="p-veteran">
                  <option value="">Prefer not to answer</option>
                  <option>I am not a protected veteran</option>
                  <option>I identify as one or more of the classifications of protected veteran</option>
                </select>
              </div>
              <div class="form-group">
                <label for="p-disability">Disability Status</label>
                <select id="p-disability">
                  <option value="">Prefer not to answer</option>
                  <option>No, I do not have a disability</option>
                  <option>Yes, I have a disability</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        <!-- Save Button / Feedback Area -->
        <div style="margin-top: 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
          <div>
            <button type="submit" class="btn btn-primary btn-lg" id="save-profile-btn">
              💾 Save Profile
            </button>
          </div>
          <div id="save-hint" class="text-sm text-muted"></div>
        </div>
      </form>

      <!-- Re-upload Diff Modal Container -->
      <div id="diff-modal-container"></div>
    `;

    // Initialize listeners
    setupEventListeners();

    // Load initial data
    await loadProfile();
  }

  function setupEventListeners() {
    // EEO toggle
    const eeoToggle = document.getElementById('eeo-toggle');
    if (eeoToggle) {
      eeoToggle.addEventListener('click', () => {
        const section = document.getElementById('eeo-section');
        const arrow = document.getElementById('eeo-arrow');
        if (section.style.display === 'none') {
          section.style.display = 'block';
          arrow.textContent = '▾';
        } else {
          section.style.display = 'none';
          arrow.textContent = '▸';
        }
      });
    }

    // Add Education
    document.getElementById('add-education-btn').addEventListener('click', () => {
      addEducationRow();
      updateLiveCompleteness();
    });

    // Add Experience
    document.getElementById('add-experience-btn').addEventListener('click', () => {
      addExperienceRow();
    });

    // Resume Dropzone & Upload
    const dropzone = document.getElementById('upload-dropzone');
    const fileInput = document.getElementById('resume-file-input');

    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = 'var(--accent)';
      dropzone.style.background = 'rgba(99, 102, 241, 0.08)';
    });
    dropzone.addEventListener('dragleave', () => {
      dropzone.style.borderColor = 'var(--border)';
      dropzone.style.background = 'transparent';
    });
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = 'var(--border)';
      dropzone.style.background = 'transparent';
      const file = e.dataTransfer.files[0];
      if (file) handleResumeUpload(file);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) {
        handleResumeUpload(fileInput.files[0]);
        fileInput.value = '';
      }
    });

    // Profile form input live validation
    const form = document.getElementById('profile-form');
    form.addEventListener('input', () => updateLiveCompleteness());
    form.addEventListener('change', () => updateLiveCompleteness());

    // Email strict override listener
    const emailInput = document.getElementById('p-email');
    if (emailInput) {
      const handleEmailChange = () => {
        if (emailInput.value.trim().toLowerCase() === 'nitinchandra834@gmail.com') {
          emailInput.value = 'codernitin55@gmail.com';
        }
        updateLiveCompleteness();
      };
      emailInput.addEventListener('input', handleEmailChange);
      emailInput.addEventListener('change', handleEmailChange);
      emailInput.addEventListener('blur', handleEmailChange);
    }

    // Submit handler
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await saveProfile();
    });
  }

  async function loadProfile() {
    try {
      const data = await profileAPI.get();
      _profile = data.profile || {};
      _user = data.user || {};
      _resumes = data.resumes || [];

      // Fill user & personal info
      setValue('p-name', _user.full_name || _profile.full_name);
      let userEmail = (_user.email || '').trim();
      if (userEmail.toLowerCase() === 'nitinchandra834@gmail.com') {
        userEmail = 'codernitin55@gmail.com';
      }
      setValue('p-email', userEmail);
      setValue('p-phone', _profile.phone);
      setValue('p-location', _profile.location);
      setValue('p-linkedin', _profile.linkedin_url);
      setValue('p-github', _profile.github_url);
      setValue('p-portfolio', _profile.portfolio_url);
      setValue('p-pronouns', _profile.pronouns);

      // Professional info
      setValue('p-title', _profile.current_title);
      setValue('p-yoe', _profile.years_of_experience);
      setValue('p-notice', _profile.notice_period);
      setValue('p-expected-ctc', _profile.expected_ctc);
      setValue('p-current-ctc', _profile.current_ctc);
      setValue('p-work-auth', _profile.work_authorization);
      setValue('p-remote', _profile.remote_preference);
      setValue('p-relocate', _profile.willing_to_relocate != null ? String(_profile.willing_to_relocate) : '');
      setValue('p-summary', _profile.summary);

      // EEO
      setValue('p-gender', _profile.gender);
      setValue('p-ethnicity', _profile.ethnicity);
      setValue('p-veteran', _profile.veteran_status);
      setValue('p-disability', _profile.disability_status);

      // Skills
      if (_profile.skills && Array.isArray(_profile.skills)) {
        setValue('p-skills', _profile.skills.join(', '));
      }

      // Education
      const eduList = document.getElementById('education-list');
      eduList.innerHTML = '';
      if (_profile.education && _profile.education.length > 0) {
        _profile.education.forEach(edu => addEducationRow(edu));
      }

      // Experience
      const expList = document.getElementById('experience-list');
      expList.innerHTML = '';
      if (_profile.experience && _profile.experience.length > 0) {
        _profile.experience.forEach(exp => addExperienceRow(exp));
      }

      // Resumes
      renderResumes();

      // Recalculate live completeness
      updateLiveCompleteness();
    } catch (err) {
      showToast('Failed to load profile: ' + err.message, 'error');
    }
  }

  function updateLiveCompleteness() {
    const missing = [];
    const filled = [];

    // 1. Name
    const nameVal = (document.getElementById('p-name')?.value || '').trim();
    if (nameVal && nameVal !== 'New User' && nameVal !== 'User') {
      filled.push('name');
      clearMissingHighlight('group-p-name');
    } else {
      missing.push({ key: 'name', label: 'Full Name' });
      setMissingHighlight('group-p-name');
    }

    // 2. Email
    const emailVal = (document.getElementById('p-email')?.value || '').trim();
    if (emailVal) {
      filled.push('email');
      clearMissingHighlight('group-p-email');
    } else {
      missing.push({ key: 'email', label: 'Email Address' });
      setMissingHighlight('group-p-email');
    }

    // 3. Phone
    const phoneVal = (document.getElementById('p-phone')?.value || '').trim();
    if (phoneVal) {
      filled.push('phone');
      clearMissingHighlight('group-p-phone');
    } else {
      missing.push({ key: 'phone', label: 'Phone Number' });
      setMissingHighlight('group-p-phone');
    }

    // 4. Location
    const locVal = (document.getElementById('p-location')?.value || '').trim();
    if (locVal) {
      filled.push('location');
      clearMissingHighlight('group-p-location');
    } else {
      missing.push({ key: 'location', label: 'Location' });
      setMissingHighlight('group-p-location');
    }

    // 5. Notice Period
    const noticeVal = (document.getElementById('p-notice')?.value || '').trim();
    if (noticeVal) {
      filled.push('notice_period');
      clearMissingHighlight('group-p-notice');
    } else {
      missing.push({ key: 'notice_period', label: 'Notice Period' });
      setMissingHighlight('group-p-notice');
    }

    // 6. Expected CTC
    const ctcVal = (document.getElementById('p-expected-ctc')?.value || '').trim();
    if (ctcVal) {
      filled.push('expected_ctc');
      clearMissingHighlight('group-p-expected-ctc');
    } else {
      missing.push({ key: 'expected_ctc', label: 'Expected Compensation' });
      setMissingHighlight('group-p-expected-ctc');
    }

    // 7. Work Authorization
    const authVal = (document.getElementById('p-work-auth')?.value || '').trim();
    if (authVal) {
      filled.push('work_authorization');
      clearMissingHighlight('group-p-work-auth');
    } else {
      missing.push({ key: 'work_authorization', label: 'Work Authorization' });
      setMissingHighlight('group-p-work-auth');
    }

    // 8. Skills
    const skillsVal = (document.getElementById('p-skills')?.value || '').trim();
    if (skillsVal) {
      filled.push('skills');
      clearMissingHighlight('group-p-skills');
    } else {
      missing.push({ key: 'skills', label: 'Skills' });
      setMissingHighlight('group-p-skills');
    }

    // 9. Education
    const eduRows = document.querySelectorAll('#education-list .dynamic-row');
    let hasValidEdu = false;
    eduRows.forEach(row => {
      const school = row.querySelector('.edu-school')?.value.trim();
      const degree = row.querySelector('.edu-degree')?.value.trim();
      if (school || degree) hasValidEdu = true;
    });

    const eduCard = document.getElementById('card-education');
    if (hasValidEdu) {
      filled.push('education');
      if (eduCard) eduCard.classList.remove('field-missing');
    } else {
      missing.push({ key: 'education', label: 'Education (At least 1 degree)' });
      if (eduCard) eduCard.classList.add('field-missing');
    }

    const totalRequired = 9;
    const percent = Math.round((filled.length / totalRequired) * 100);
    const isComplete = (missing.length === 0);

    // Update Banner UI
    const pctText = document.getElementById('completeness-pct-text');
    const badge = document.getElementById('completeness-badge');
    const fill = document.getElementById('completeness-bar-fill');
    const summary = document.getElementById('completeness-summary');
    const tagsContainer = document.getElementById('missing-tags-container');
    const saveBtn = document.getElementById('save-profile-btn');
    const saveHint = document.getElementById('save-hint');

    if (pctText) {
      pctText.textContent = `${percent}%`;
      pctText.className = `completeness-pct ${isComplete ? 'complete' : 'incomplete'}`;
    }

    if (fill) {
      fill.style.width = `${percent}%`;
      fill.className = `completeness-bar-fill ${isComplete ? 'complete' : 'incomplete'}`;
    }

    if (badge) {
      if (isComplete) {
        badge.className = 'badge badge-success';
        badge.textContent = '✓ 100% Complete';
      } else {
        badge.className = 'badge badge-warning';
        badge.textContent = `${missing.length} Missing`;
      }
    }

    if (summary) {
      if (isComplete) {
        summary.innerHTML = '<span class="text-success">All required fields are completed. 1-Click apply is enabled!</span>';
      } else {
        summary.textContent = `${filled.length} of ${totalRequired} required fields completed`;
      }
    }

    if (tagsContainer) {
      if (isComplete) {
        tagsContainer.innerHTML = '<span class="filled-all-tag">✓ Ready to auto-apply across Greenhouse, Lever, Ashby, and Workable</span>';
      } else {
        tagsContainer.innerHTML = missing.map(m =>
          `<span class="missing-tag">⚠ ${escapeHtml(m.label)}</span>`
        ).join('');
      }
    }

    // Save Button state: Always enabled so users can edit and save any changes at any time
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.classList.remove('btn-secondary');
      saveBtn.classList.add('btn-primary');
      if (isComplete) {
        saveBtn.innerHTML = '💾 Save Profile (100% Ready)';
        if (saveHint) saveHint.innerHTML = '<span class="text-success">Profile complete & ready for 1-click apply!</span>';
      } else {
        saveBtn.innerHTML = '💾 Save Profile';
        if (saveHint) saveHint.innerHTML = `<span class="text-warning">Note: ${missing.length} required field${missing.length > 1 ? 's' : ''} still needed to unlock 1-click apply.</span>`;
      }
    }
  }

  function setMissingHighlight(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('field-missing');
  }

  function clearMissingHighlight(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('field-missing');
  }

  function addEducationRow(data = {}) {
    const list = document.getElementById('education-list');
    if (!list) return;

    const row = document.createElement('div');
    row.className = 'dynamic-row';
    row.innerHTML = `
      <div class="form-grid form-grid-4">
        <div class="form-group">
          <label>Degree / Certificate</label>
          <input type="text" class="edu-degree" value="${escapeAttr(data.degree || '')}" placeholder="B.S. Computer Science" />
        </div>
        <div class="form-group">
          <label>Field of Study</label>
          <input type="text" class="edu-field" value="${escapeAttr(data.field || '')}" placeholder="Software Engineering" />
        </div>
        <div class="form-group">
          <label>University / School</label>
          <input type="text" class="edu-school" value="${escapeAttr(data.school || data.institute || '')}" placeholder="Stanford University" />
        </div>
        <div class="form-group">
          <label>Graduation Year</label>
          <input type="text" class="edu-year" value="${escapeAttr(data.graduation_year || data.end_year || '')}" placeholder="2023" />
        </div>
      </div>
      <button type="button" class="btn btn-xs btn-ghost remove-row-btn" title="Remove" style="margin-top: 8px;">✕ Remove</button>
    `;

    row.querySelector('.remove-row-btn').addEventListener('click', () => {
      row.remove();
      updateLiveCompleteness();
    });

    row.querySelectorAll('input').forEach(inp => {
      inp.addEventListener('input', () => updateLiveCompleteness());
    });

    list.appendChild(row);
  }

  function addExperienceRow(data = {}) {
    const list = document.getElementById('experience-list');
    if (!list) return;

    let company = data.company || '';
    let startDate = data.start_date || '';
    let endDate = data.end_date || '';

    // Clean dates if accidentally attached to company name
    const dateRangeMatch = company.match(/^(.*?)\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\s*(?:–|—|-|to|\ufffd|\u2013|\u2014)\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|Present|Current)/i);
    if (dateRangeMatch) {
      company = dateRangeMatch[1].trim();
      if (!startDate || startDate.length <= 4) startDate = dateRangeMatch[2].trim();
      if (!endDate || endDate.length <= 4) endDate = dateRangeMatch[3].trim();
    }

    const row = document.createElement('div');
    row.className = 'dynamic-row';
    row.innerHTML = `
      <div class="form-grid form-grid-4">
        <div class="form-group">
          <label>Company / Organization</label>
          <input type="text" class="exp-company" value="${escapeAttr(company)}" placeholder="e.g. IDEMIA, Paytm" />
        </div>
        <div class="form-group">
          <label>Job Title / Role</label>
          <input type="text" class="exp-title" value="${escapeAttr(data.title || '')}" placeholder="e.g. Python Developer Intern" />
        </div>
        <div class="form-group">
          <label>Start Date (e.g. Jun 2026 or 01/06/2026)</label>
          <input type="text" class="exp-start" value="${escapeAttr(startDate)}" placeholder="e.g. Jun 2026" />
        </div>
        <div class="form-group">
          <label>End Date (e.g. Jul 2026 or Present)</label>
          <input type="text" class="exp-end" value="${escapeAttr(endDate)}" placeholder="e.g. Jul 2026 / Present" />
        </div>
      </div>
      <div class="form-group" style="margin-top: 8px;">
        <label>Key Responsibilities & Achievements</label>
        <textarea class="exp-desc" rows="3" placeholder="Key responsibilities and achievements…">${escapeHtml(data.description || '')}</textarea>
      </div>
      <button type="button" class="btn btn-xs btn-ghost remove-row-btn" title="Remove" style="margin-top: 4px; color: var(--error);">✕ Remove This Experience</button>
    `;

    row.querySelector('.remove-row-btn').addEventListener('click', () => {
      row.remove();
      updateLiveCompleteness();
    });

    row.querySelectorAll('input, textarea').forEach(inp => {
      inp.addEventListener('input', () => updateLiveCompleteness());
    });

    list.appendChild(row);
  }

  async function handleResumeUpload(file) {
    const allowed = ['.pdf', '.docx'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();

    if (!allowed.includes(ext)) {
      showToast(`Invalid file format '${ext}'. Please upload a PDF or DOCX file.`, 'warning');
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      showToast(`File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds maximum allowed limit of 5 MB.`, 'error');
      return;
    }

    const dropContent = document.getElementById('upload-dropzone-content');
    const dropLoading = document.getElementById('upload-dropzone-loading');

    if (dropContent) dropContent.style.display = 'none';
    if (dropLoading) dropLoading.style.display = 'block';

    showToast('Uploading and parsing resume with AI…', 'info', 4000);

    try {
      const data = await resumeAPI.upload(file);

      // Check if re-upload has significant differences against existing fields
      const diff = data.diff || {};
      const changedKeys = Object.keys(diff).filter(k => diff[k]?.changed);

      if (changedKeys.length > 0 && hasExistingData()) {
        _pendingDiff = { diff, parsed: data.parsed, file };
        showDiffModal(diff, data.parsed);
      } else {
        // Apply directly to form
        applyParsedDataToForm(data.parsed, true);
        showToast('Resume parsed successfully! All internships and details prefilled.', 'success');
      }

      if (data.resume) {
        _resumes = [data.resume, ..._resumes.filter(r => r.id !== data.resume.id)];
        renderResumes();
      }
      updateLiveCompleteness();
    } catch (err) {
      showToast('Resume parsing error: ' + err.message, 'error');
    } finally {
      if (dropContent) dropContent.style.display = 'block';
      if (dropLoading) dropLoading.style.display = 'none';
    }
  }

  function hasExistingData() {
    const phone = document.getElementById('p-phone')?.value.trim();
    const loc = document.getElementById('p-location')?.value.trim();
    const skills = document.getElementById('p-skills')?.value.trim();
    return Boolean(phone || loc || skills);
  }

  function applyParsedDataToForm(parsed, forceOverwrite = false) {
    if (!parsed) return;

    // Contact
    if (parsed.email) {
      let pEmail = parsed.email.trim();
      if (pEmail.toLowerCase() === 'nitinchandra834@gmail.com') {
        pEmail = 'codernitin55@gmail.com';
      }
      if (forceOverwrite || !document.getElementById('p-email')?.value.trim()) {
        setValue('p-email', pEmail);
      }
    }
    if (parsed.full_name && (forceOverwrite || !document.getElementById('p-name')?.value.trim())) {
      setValue('p-name', parsed.full_name);
    }
    if (parsed.phone && (forceOverwrite || !document.getElementById('p-phone')?.value.trim())) {
      setValue('p-phone', parsed.phone);
    }
    if (parsed.location && (forceOverwrite || !document.getElementById('p-location')?.value.trim())) {
      setValue('p-location', parsed.location);
    }

    // Links
    if (parsed.linkedin && (forceOverwrite || !document.getElementById('p-linkedin')?.value.trim())) {
      setValue('p-linkedin', parsed.linkedin);
    }
    if (parsed.github && (forceOverwrite || !document.getElementById('p-github')?.value.trim())) {
      setValue('p-github', parsed.github);
    }
    if (parsed.portfolio && (forceOverwrite || !document.getElementById('p-portfolio')?.value.trim())) {
      setValue('p-portfolio', parsed.portfolio);
    }

    // Summary
    if (parsed.summary && (forceOverwrite || !document.getElementById('p-summary')?.value.trim())) {
      setValue('p-summary', parsed.summary);
    }

    // Skills
    if (parsed.skills && Array.isArray(parsed.skills) && parsed.skills.length > 0) {
      const existing = (document.getElementById('p-skills')?.value || '')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
      const combined = forceOverwrite ? parsed.skills : Array.from(new Set([...existing, ...parsed.skills]));
      setValue('p-skills', combined.join(', '));
    }

    // Education
    if (parsed.education && Array.isArray(parsed.education) && parsed.education.length > 0) {
      const eduList = document.getElementById('education-list');
      if (eduList) {
        eduList.innerHTML = '';
        parsed.education.forEach(edu => addEducationRow(edu));
      }
    }

    // Experience (All internships and jobs)
    if (parsed.experience && Array.isArray(parsed.experience) && parsed.experience.length > 0) {
      const expList = document.getElementById('experience-list');
      if (expList) {
        expList.innerHTML = '';
        parsed.experience.forEach(exp => addExperienceRow(exp));
      }
    }

    updateLiveCompleteness();
  }

  function showDiffModal(diff, parsed) {
    const modalContainer = document.getElementById('diff-modal-container');
    if (!modalContainer) return;

    const changedKeys = Object.keys(diff).filter(k => diff[k]?.changed);
    if (changedKeys.length === 0) return;

    let rowsHtml = '';
    for (const key of changedKeys) {
      const item = diff[key];
      const curStr = typeof item.current === 'object' ? JSON.stringify(item.current) : String(item.current || '(empty)');
      const newStr = typeof item.parsed === 'object' ? JSON.stringify(item.parsed) : String(item.parsed || '(empty)');

      rowsHtml += `
        <tr>
          <td style="font-weight: 600; text-transform: capitalize;">${escapeHtml(key.replace(/_/g, ' '))}</td>
          <td class="diff-old">${escapeHtml(curStr.slice(0, 100))}</td>
          <td class="diff-new">${escapeHtml(newStr.slice(0, 100))}</td>
        </tr>
      `;
    }

    modalContainer.innerHTML = `
      <div class="diff-modal-backdrop" id="diff-modal-backdrop">
        <div class="diff-modal-box">
          <h3 style="margin-top: 0; display: flex; align-items: center; gap: 8px;">
            <span>🔄</span> Resume Re-upload: Changed Fields Detected
          </h3>
          <p class="text-muted text-sm">
            We extracted new information from your uploaded resume that differs from your current profile.
            Choose whether to update your profile with the new data or keep your current entries intact.
          </p>

          <table class="diff-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Current Value</th>
                <th>Detected from Resume</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>

          <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px;">
            <button type="button" class="btn btn-ghost" id="diff-reject-btn">Keep Current Values</button>
            <button type="button" class="btn btn-primary" id="diff-accept-btn">Accept & Overwrite Changes</button>
          </div>
        </div>
      </div>
    `;

    document.getElementById('diff-accept-btn').addEventListener('click', () => {
      applyParsedDataToForm(parsed, true);
      closeDiffModal();
      showToast('Profile updated with newly extracted resume fields!', 'success');
    });

    document.getElementById('diff-reject-btn').addEventListener('click', () => {
      closeDiffModal();
      showToast('Kept existing profile entries.', 'info');
    });
  }

  function closeDiffModal() {
    const modalContainer = document.getElementById('diff-modal-container');
    if (modalContainer) modalContainer.innerHTML = '';
    _pendingDiff = null;
  }

  async function saveProfile() {
    const btn = document.getElementById('save-profile-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-sm"></span> Saving…';

    // Collect education
    const education = [];
    document.querySelectorAll('#education-list .dynamic-row').forEach(row => {
      education.push({
        degree: row.querySelector('.edu-degree')?.value.trim() || '',
        field: row.querySelector('.edu-field')?.value.trim() || '',
        school: row.querySelector('.edu-school')?.value.trim() || '',
        graduation_year: row.querySelector('.edu-year')?.value.trim() || '',
      });
    });

    // Collect experience
    const experience = [];
    document.querySelectorAll('#experience-list .dynamic-row').forEach(row => {
      experience.push({
        company: row.querySelector('.exp-company')?.value.trim() || '',
        title: row.querySelector('.exp-title')?.value.trim() || '',
        start_date: row.querySelector('.exp-start')?.value.trim() || '',
        end_date: row.querySelector('.exp-end')?.value.trim() || '',
        description: row.querySelector('.exp-desc')?.value.trim() || '',
      });
    });

    // Skills
    const skillsRaw = document.getElementById('p-skills')?.value || '';
    const skills = skillsRaw.split(',').map(s => s.trim()).filter(Boolean);

    // Email (with strict override of nitinchandra834@gmail.com)
    let emailVal = (document.getElementById('p-email')?.value || '').trim();
    if (emailVal.toLowerCase() === 'nitinchandra834@gmail.com') {
      emailVal = 'codernitin55@gmail.com';
      setValue('p-email', emailVal);
    }

    const payload = {
      email: emailVal,
      full_name: document.getElementById('p-name')?.value.trim(),
      name: document.getElementById('p-name')?.value.trim(),
      phone: document.getElementById('p-phone')?.value.trim(),
      location: document.getElementById('p-location')?.value.trim(),
      linkedin_url: document.getElementById('p-linkedin')?.value.trim(),
      github_url: document.getElementById('p-github')?.value.trim(),
      portfolio_url: document.getElementById('p-portfolio')?.value.trim(),
      pronouns: document.getElementById('p-pronouns')?.value.trim(),
      current_title: document.getElementById('p-title')?.value.trim(),
      years_of_experience: parseInt(document.getElementById('p-yoe')?.value) || null,
      notice_period: document.getElementById('p-notice')?.value.trim(),
      expected_ctc: document.getElementById('p-expected-ctc')?.value.trim(),
      current_ctc: document.getElementById('p-current-ctc')?.value.trim(),
      work_authorization: document.getElementById('p-work-auth')?.value,
      remote_preference: document.getElementById('p-remote')?.value,
      willing_to_relocate: document.getElementById('p-relocate')?.value === 'true' ? true :
                           document.getElementById('p-relocate')?.value === 'false' ? false : null,
      summary: document.getElementById('p-summary')?.value.trim(),
      gender: document.getElementById('p-gender')?.value,
      ethnicity: document.getElementById('p-ethnicity')?.value,
      veteran_status: document.getElementById('p-veteran')?.value,
      disability_status: document.getElementById('p-disability')?.value,
      skills,
      education,
      experience,
    };

    try {
      const res = await profileAPI.complete(payload);
      showToast('Profile saved successfully! 💾', 'success');
      if (res && res.is_complete) {
        showToast('All required fields complete! 1-Click apply is unlocked 🚀', 'success', 3500);
      }
    } catch (err) {
      showToast('Failed to save profile: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '💾 Save Profile';
      updateLiveCompleteness();
    }
  }

  function renderResumes() {
    const container = document.getElementById('resume-list');
    if (!container) return;

    if (!_resumes || _resumes.length === 0) {
      container.innerHTML = '<p class="text-muted text-sm">No resumes uploaded yet.</p>';
      return;
    }

    let html = '<h4 style="margin: 0 0 10px 0; font-size: 0.9rem;">Uploaded Resumes:</h4>';
    for (const r of _resumes) {
      const primary = r.is_primary ? '<span class="badge badge-success" style="margin-left: 8px;">Primary</span>' : '';
      const primaryBtn = r.is_primary ? '' :
        `<button class="btn btn-xs btn-ghost set-primary-btn" data-id="${r.id}">Set Primary</button>`;

      const sizeKb = r.file_size ? `${Math.round(r.file_size / 1024)} KB` : '';

      html += `
        <div class="resume-item" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius-md); margin-bottom: 8px;">
          <div class="resume-info" style="display: flex; align-items: center; gap: 8px;">
            <span class="resume-name" style="font-weight: 600;">📄 ${escapeHtml(r.original_filename)}</span>
            <span class="text-muted text-xs">${sizeKb}</span>
            ${primary}
          </div>
          <div class="resume-actions" style="display: flex; gap: 8px;">
            ${primaryBtn}
            <button class="btn btn-xs btn-ghost delete-resume-btn" data-id="${r.id}" style="color: var(--error);">🗑 Delete</button>
          </div>
        </div>
      `;
    }
    container.innerHTML = html;

    container.querySelectorAll('.set-primary-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          await profileAPI.setPrimaryResume(btn.dataset.id);
          showToast('Primary resume updated', 'success');
          await loadProfile();
        } catch (err) {
          showToast(err.message, 'error');
        }
      });
    });

    container.querySelectorAll('.delete-resume-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to delete this resume?')) return;
        try {
          await profileAPI.deleteResume(btn.dataset.id);
          showToast('Resume deleted', 'info');
          await loadProfile();
        } catch (err) {
          showToast(err.message, 'error');
        }
      });
    });
  }

  function setValue(id, value) {
    const el = document.getElementById(id);
    if (el && value != null) el.value = value;
  }

  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function escapeAttr(str) {
    return (str || '').replace(/"/g, '&quot;');
  }

  return { render };
})();
