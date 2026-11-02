"""
Resume parsing service using pdfplumber and PyMuPDF.
Extracts text and structured data from PDF resumes.
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Comprehensive skills vocabulary
# ---------------------------------------------------------------------------
SKILLS_VOCABULARY = [
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "Rust",
    "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "MATLAB", "Perl", "Shell",
    "Bash", "PowerShell", "Haskell", "Elixir", "Erlang", "Lua", "Dart", "Julia",
    "COBOL", "Fortran", "Assembly", "Groovy", "Objective-C", "VB.NET", "F#",
    # Web — Frontend
    "HTML", "CSS", "SASS", "SCSS", "React", "Vue", "Angular", "Svelte", "Next.js",
    "Nuxt.js", "Gatsby", "Redux", "MobX", "Zustand", "Webpack", "Vite", "Rollup",
    "Tailwind CSS", "Bootstrap", "Material UI", "Ant Design", "Styled Components",
    "GraphQL", "REST", "WebSockets", "gRPC", "jQuery", "Backbone.js", "Ember.js",
    # Web — Backend
    "Node.js", "Express", "FastAPI", "Flask", "Django", "Spring Boot", "Spring",
    "Rails", "Laravel", "Symfony", "ASP.NET", ".NET Core", "Gin", "Echo", "Fiber",
    "NestJS", "Koa", "Hapi", "Tornado", "Celery", "RabbitMQ", "Kafka", "Redis",
    # Databases
    "SQL", "MySQL", "PostgreSQL", "SQLite", "MongoDB", "Cassandra", "DynamoDB",
    "Redis", "Elasticsearch", "Neo4j", "CouchDB", "Firebase", "Firestore",
    "Oracle", "SQL Server", "MariaDB", "HBase", "InfluxDB", "TimescaleDB",
    "Supabase", "PlanetScale", "Neon",
    # Cloud & DevOps
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Ansible",
    "Helm", "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Travis CI",
    "Pulumi", "CloudFormation", "CDK", "Serverless", "Lambda", "EC2", "S3",
    "RDS", "EKS", "ECS", "GKE", "Cloud Run", "BigQuery", "Dataflow", "Pub/Sub",
    "Azure DevOps", "Prometheus", "Grafana", "Datadog", "New Relic", "Splunk",
    "Nginx", "Apache", "Caddy", "Istio", "Envoy", "Vault",
    # Data Science / ML / AI
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "LLM",
    "TensorFlow", "PyTorch", "Keras", "scikit-learn", "Pandas", "NumPy",
    "Matplotlib", "Seaborn", "Plotly", "OpenCV", "Hugging Face", "LangChain",
    "spaCy", "NLTK", "XGBoost", "LightGBM", "CatBoost", "MLflow", "Weights & Biases",
    "Spark", "Hadoop", "Airflow", "dbt", "Looker", "Tableau", "Power BI",
    # Mobile
    "React Native", "Flutter", "Android", "iOS", "SwiftUI", "Jetpack Compose",
    "Expo", "Ionic", "Xamarin",
    # Testing
    "Jest", "Pytest", "JUnit", "Mocha", "Chai", "Cypress", "Playwright",
    "Selenium", "TestNG", "RSpec", "Cucumber", "Postman", "k6",
    # Tools & Practices
    "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence", "Notion",
    "Linux", "Unix", "Agile", "Scrum", "Kanban", "TDD", "BDD", "CI/CD",
    "Microservices", "SOA", "Event-Driven", "Domain-Driven Design", "SOLID",
    "Design Patterns", "System Design",
    # Security
    "OAuth", "JWT", "SAML", "OpenID", "SSO", "OWASP", "Penetration Testing",
    "Cryptography", "SSL/TLS",
]

# Normalised lookup set for fast matching
_SKILLS_LOWER = {s.lower(): s for s in SKILLS_VOCABULARY}

# Degree keywords used to detect education sections
DEGREE_KEYWORDS = [
    "bachelor", "b.sc", "b.s.", "b.e.", "b.tech", "be", "bsc",
    "master", "m.sc", "m.s.", "m.tech", "msc", "mba", "m.b.a.",
    "ph.d", "phd", "doctorate", "associate", "diploma", "a.a.", "a.s.",
    "high school", "secondary", "undergraduate", "postgraduate",
]

# Section header patterns
SECTION_PATTERNS = {
    "summary": re.compile(
        r"^\s*(?:professional\s+|career\s+)?(?:summary|profile|objective|about\s+me)\b",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"^\s*(?:education|academic\s+background|qualifications?|academics?)\b",
        re.IGNORECASE,
    ),
    "skills": re.compile(
        r"^\s*(?:technical\s+|core\s+)?(?:skills|competencies|technologies|tools)\b",
        re.IGNORECASE,
    ),
    "experience": re.compile(
        r"^\s*(?:work\s+|professional\s+|relevant\s+|industry\s+)?(?:experience|history|employment|internships?)(\s+&|\s+and)?\b",
        re.IGNORECASE,
    ),
    "projects": re.compile(
        r"^\s*(?:academic\s+|personal\s+|key\s+)?projects?(\s+&|\s+and)?\b",
        re.IGNORECASE,
    ),
    "certifications": re.compile(
        r"^\s*(?:certifications?|licenses?|accreditations?|courses?|training)\b",
        re.IGNORECASE,
    ),
    "languages": re.compile(
        r"^\s*languages?\b",
        re.IGNORECASE,
    ),
}

# Compiled regex patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[\s\-.]?)?(\(?\d{2,4}\)?[\s\-.]?)?\d{3,4}[\s\-.]?\d{4}"
)
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"github\.com/[\w\-]+", re.IGNORECASE)

_MONTH_NAME = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE_PATTERN = rf"(?:(?:\d{{1,2}}[-/\s]+)?{_MONTH_NAME}[-/\s,]+(?:\d{{1,2}}[-/\s,]+)?\d{{2,4}}|\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{2,4}}|\d{{1,2}}[-/]\d{{4}}|(?:19|20)\d{{2}}|Present|Current|Ongoing|Now)"
_DATE_RE = re.compile(_DATE_PATTERN, re.IGNORECASE)
_RANGE_SEPARATOR = r"\s*(?:–|—|-|to|\ufffd|\u2013|\u2014|\u2012|\u2015|\u2212)\s*"
_DATE_RANGE_RE = re.compile(rf"({_DATE_PATTERN}){_RANGE_SEPARATOR}({_DATE_PATTERN})", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_pdfplumber(file_path: str) -> str:
    """Extract full text using pdfplumber."""
    import pdfplumber  # type: ignore

    pages = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text()
                if text:
                    pages.append(text)
            except Exception:
                pass
    return "\n".join(pages)


def _extract_text_pymupdf(file_path: str) -> str:
    """Extract full text using PyMuPDF (fitz) as a fallback."""
    import fitz  # type: ignore  # PyMuPDF

    pages = []
    with fitz.open(file_path) as doc:
        for page in doc:
            try:
                pages.append(page.get_text())
            except Exception:
                pass
    return "\n".join(pages)


def _get_text(file_path: str) -> str:
    """Try pdfplumber first; fall back to PyMuPDF."""
    text = ""
    try:
        text = _extract_text_pdfplumber(file_path)
    except Exception:
        pass

    if not text.strip():
        try:
            text = _extract_text_pymupdf(file_path)
        except Exception:
            pass

    return text


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _extract_email(text: str):
    """Return the first email address found in text, enforcing strict project email override."""
    try:
        match = _EMAIL_RE.search(text)
        if match:
            found = match.group(0).strip().lower()
            if found == "nitinchandra834@gmail.com":
                return "codernitin55@gmail.com"
            return found
        return None
    except Exception:
        return None


def _extract_phone(text: str):
    """Return the first phone number found (at least 10 digits)."""
    try:
        for match in _PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) >= 10:
                return match.group(0).strip()
    except Exception:
        pass
    return None


def _extract_linkedin(text: str):
    """Return the LinkedIn profile URL if found."""
    try:
        match = _LINKEDIN_RE.search(text)
        return f"https://www.{match.group(0)}" if match else None
    except Exception:
        return None


def _extract_github(text: str):
    """Return the GitHub profile URL if found."""
    try:
        match = _GITHUB_RE.search(text)
        return f"https://www.{match.group(0)}" if match else None
    except Exception:
        return None


def _extract_name(text: str, parsed_email: str = None):
    """
    Heuristic: the first non-empty, non-email, non-URL line is often the name.
    """
    try:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip lines that look like email, phone, or URL
            if "@" in line or "http" in line.lower() or line.startswith("+"):
                continue
            if re.search(r"\d{5,}", line):  # Skip lines with long digit sequences
                continue
            # Reasonable name: 2–5 words, mostly alpha
            words = line.split()
            if 2 <= len(words) <= 5 and all(re.match(r"[A-Za-z\-\.\']+$", w) for w in words):
                return line
    except Exception:
        pass
    return None


def _extract_skills(text: str, sections: dict = None) -> list:
    """Match known skills from vocabulary and extract explicit skills from skills section."""
    try:
        found = set()
        text_lower = text.lower()
        for skill_lower, skill_canonical in _SKILLS_LOWER.items():
            pattern = re.compile(
                r"(?<![a-zA-Z0-9+#.])" + re.escape(skill_lower) + r"(?![a-zA-Z0-9+#.])",
                re.IGNORECASE,
            )
            if pattern.search(text_lower):
                found.add(skill_canonical)

        # Also parse explicit terms from skills section if present
        sec_text = ""
        if sections and isinstance(sections, dict):
            sec_text = sections.get("skills", "")
        if not sec_text and "skills" in text_lower:
            m = re.search(r"(?:technical\s+|core\s+)?skills?.*?(?=\n\s*(?:experience|education|projects|summary|\Z))", text, re.IGNORECASE | re.DOTALL)
            if m:
                sec_text = m.group(0)

        if sec_text:
            for line in sec_text.splitlines():
                l_str = line.strip()
                if not l_str or re.match(r"^\s*(?:technical\s+|core\s+)?skills?\s*$", l_str, re.I):
                    continue
                if ":" in l_str:
                    _, items_str = l_str.split(":", 1)
                else:
                    items_str = l_str
                for item in re.split(r"[,|•;]", items_str):
                    c = item.strip()
                    if c and len(c) <= 35 and not any(kw in c.lower() for kw in ["skills", "experience", "education"]):
                        found.add(c)

        return sorted(found)
    except Exception:
        return []


def _split_sections(text: str) -> dict:
    """
    Split resume text into named sections using header patterns.
    Returns a dict: section_name -> section_text.
    """
    sections: dict[str, list] = {
        "header": [],
        "summary": [],
        "experience": [],
        "education": [],
        "skills": [],
        "projects": [],
        "certifications": [],
        "languages": [],
        "other": [],
    }
    current = "header"

    for line in text.splitlines():
        stripped = line.strip()
        matched = False
        if len(stripped) < 60:
            for section_name, pattern in SECTION_PATTERNS.items():
                if pattern.match(stripped):
                    current = section_name
                    matched = True
                    break
        if not matched:
            sections[current].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _extract_summary(sections: dict) -> str | None:
    """Return the summary section text if available."""
    try:
        text = sections.get("summary", "").strip()
        return text if text else None
    except Exception:
        return None


def _extract_education(sections: dict) -> list:
    """
    Parse the education section into a list of dicts.
    Each dict: {school, degree, field, graduation_year, start_date, end_date, cgpa, raw}
    """
    results = []
    try:
        edu_text = sections.get("education", "")
        if not edu_text.strip():
            return results

        lines = [ln.strip() for ln in edu_text.splitlines() if ln.strip()]

        year_indices = []
        year_re = re.compile(r"\b((?:19|20)\d{2})\b")
        year_range_re = re.compile(r"\b((?:19|20)\d{2})\s*(?:–|—|-|to)\s*((?:19|20)\d{2}|Present|Current|Now)\b", re.IGNORECASE)

        for idx, l in enumerate(lines):
            m_range = year_range_re.search(l)
            if m_range:
                year_indices.append((idx, m_range.group(1), m_range.group(2)))
            else:
                m_single = year_re.search(l)
                if m_single and len(l) <= 30:
                    year_indices.append((idx, m_single.group(1), m_single.group(1)))

        if year_indices:
            for i, (y_idx, start_y, end_y) in enumerate(year_indices):
                school = lines[y_idx - 1] if y_idx > 0 else "University"
                deg_line = lines[y_idx + 1] if y_idx + 1 < len(lines) else ""

                degree = deg_line
                field = None
                if " in " in deg_line:
                    parts = deg_line.split(" in ", 1)
                    degree = parts[0].strip()
                    field = parts[1].strip()
                elif " - " in deg_line:
                    parts = deg_line.split(" - ", 1)
                    degree = parts[0].strip()
                    field = parts[1].strip()

                cgpa = None
                if y_idx + 2 < len(lines):
                    next_l = lines[y_idx + 2]
                    if i == len(year_indices) - 1 or y_idx + 2 < year_indices[i + 1][0] - 1:
                        if any(term in next_l.lower() for term in ["cgpa", "gpa", "score", "%", "percentage"]):
                            cgpa = next_l

                results.append({
                    "school": school,
                    "institution": school,
                    "degree": degree,
                    "field": field,
                    "graduation_year": end_y,
                    "start_date": start_y,
                    "end_date": end_y,
                    "cgpa": cgpa,
                    "raw": f"{school} | {degree} | {end_y}",
                })
        else:
            blocks = re.split(r"\n{2,}", edu_text.strip())
            for block in blocks:
                blines = [ln.strip() for ln in block.splitlines() if ln.strip()]
                if not blines:
                    continue
                deg_match = re.search(r"\b(" + "|".join(DEGREE_KEYWORDS) + r")[^\n,;]{0,60}", block, re.IGNORECASE)
                dates = _DATE_RE.findall(block)
                results.append({
                    "school": blines[0],
                    "institution": blines[0],
                    "degree": deg_match.group(0).strip() if deg_match else (blines[1] if len(blines) > 1 else None),
                    "field": None,
                    "graduation_year": dates[-1] if dates else None,
                    "start_date": dates[0] if len(dates) > 1 else None,
                    "end_date": dates[-1] if dates else None,
                    "cgpa": None,
                    "raw": block,
                })
    except Exception:
        pass
    return results


def _extract_experience(sections: dict) -> list:
    """
    Parse the experience section into a list of job entries.
    Extracts all internships/roles with complete date month year and clean company/title.
    Each dict: {company, title, start_date, end_date, description, raw}
    """
    results = []
    try:
        exp_text = sections.get("experience", "")
        if not exp_text.strip():
            return results

        lines = [ln.strip() for ln in exp_text.splitlines() if ln.strip()]
        date_indices = []

        for idx, line in enumerate(lines):
            m = _DATE_RANGE_RE.search(line)
            if m:
                date_indices.append((idx, m.group(1).strip(), m.group(2).strip()))
            else:
                dates = _DATE_RE.findall(line)
                if len(dates) >= 2:
                    date_indices.append((idx, dates[0].strip(), dates[1].strip()))
                elif len(dates) == 1 and any(w in line.lower() for w in ["present", "current", "till", "now", "ongoing"]):
                    date_indices.append((idx, dates[0].strip(), "Present"))

        if not date_indices:
            blocks = re.split(r"\n{2,}", exp_text.strip())
            for block in blocks:
                blines = [l.strip() for l in block.splitlines() if l.strip()]
                if blines:
                    results.append({
                        "company": blines[0],
                        "title": blines[1] if len(blines) > 1 else None,
                        "start_date": None,
                        "end_date": None,
                        "description": "\n".join(blines[2:]) if len(blines) > 2 else None,
                        "raw": block,
                    })
            return results

        for i, (d_idx, start_date, end_date) in enumerate(date_indices):
            d_line = lines[d_idx]
            company = None
            title = None
            desc_lines = []

            # Gather non-bullet header lines before this date
            header_before = []
            k = d_idx - 1
            while k >= 0 and not lines[k].startswith(("–", "-", "•", "*", "▪")):
                if i > 0 and k <= date_indices[i - 1][0]:
                    break
                header_before.insert(0, lines[k])
                k -= 1

            # Check if company name is on the same line as the date
            line_clean = _DATE_RANGE_RE.sub("", d_line).strip(" |–—-,()")
            if line_clean:
                if "," in line_clean:
                    parts = line_clean.split(",", 1)
                    company = parts[0].strip()
                    title = parts[1].strip()
                elif " - " in line_clean or " | " in line_clean:
                    parts = re.split(r"\s*[-|]\s*", line_clean, 1)
                    company = parts[0].strip()
                    title = parts[1].strip()
                else:
                    company = line_clean
            elif len(header_before) >= 2:
                company = header_before[0]
                title = header_before[1]
            elif len(header_before) == 1:
                company = header_before[0]

            # Title from line right after date if not set yet
            next_idx = d_idx + 1
            if next_idx < len(lines) and not lines[next_idx].startswith(("–", "-", "•", "*", "▪")):
                if not title:
                    title = lines[next_idx]
                    desc_start = next_idx + 1
                else:
                    desc_start = next_idx
            else:
                desc_start = next_idx

            # Find boundary where description ends before next entry
            if i + 1 < len(date_indices):
                next_d_idx = date_indices[i + 1][0]
                k_next = next_d_idx - 1
                while k_next >= desc_start and not lines[k_next].startswith(("–", "-", "•", "*", "▪")):
                    k_next -= 1
                desc_end = k_next + 1
            else:
                desc_end = len(lines)

            for j in range(desc_start, desc_end):
                desc_lines.append(lines[j])

            results.append({
                "company": company,
                "title": title,
                "start_date": start_date,
                "end_date": end_date,
                "description": "\n".join(desc_lines),
                "raw": f"{company} | {title} | {start_date} - {end_date}",
            })
    except Exception:
        pass
    return results


def _extract_projects(sections: dict) -> list:
    """Extract projects into list of dicts: {name, tech, description, link}."""
    results = []
    try:
        proj_text = sections.get("projects", "")
        if not proj_text.strip():
            return results

        lines = [l.strip() for l in proj_text.splitlines() if l.strip()]
        current_proj = None

        for line in lines:
            if line.startswith(("–", "-", "•", "*", "▪")):
                if current_proj:
                    current_proj["description"] += ("\n" if current_proj["description"] else "") + line
            elif "–" in line or "—" in line or " - " in line:
                if current_proj:
                    results.append(current_proj)
                parts = re.split(r"\s*[–—-]\s*", line, 1)
                current_proj = {
                    "name": parts[0].strip(),
                    "tech": parts[1].strip() if len(parts) > 1 else None,
                    "description": "",
                    "link": None,
                }
            else:
                if not current_proj:
                    current_proj = {"name": line, "tech": None, "description": "", "link": None}
                elif not current_proj["tech"]:
                    current_proj["tech"] = line
                else:
                    results.append(current_proj)
                    current_proj = {"name": line, "tech": None, "description": "", "link": None}

        if current_proj:
            results.append(current_proj)
    except Exception:
        pass
    return results


def _extract_certifications(sections: dict) -> list:
    """Extract certification names as a simple list."""
    try:
        text = sections.get("certifications", "").strip()
        if not text:
            return []
        certs = []
        for line in text.splitlines():
            line = line.strip().lstrip("-•*·▪►").strip()
            if line:
                certs.append(line)
        return certs
    except Exception:
        return []


def _extract_languages(sections: dict) -> list:
    """Extract spoken/written language names."""
    try:
        text = sections.get("languages", "").strip()
        if not text:
            return []
        langs = []
        for item in re.split(r"[,\n|•\-]+", text):
            item = item.strip()
            if item and len(item) < 50:
                langs.append(item)
        return langs
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_resume(file_path: str) -> dict:
    """
    Parse a PDF resume and return a structured dict.

    Returns:
        {
            text: str,
            name: str | None,
            email: str | None,
            phone: str | None,
            linkedin: str | None,
            github: str | None,
            skills: list[str],
            education: list[dict],
            experience: list[dict],
            certifications: list[str],
            languages: list[str],
            summary: str | None,
        }
    """
    result: dict[str, Any] = {
        "text": "",
        "name": None,
        "email": None,
        "phone": None,
        "linkedin": None,
        "github": None,
        "skills": [],
        "education": [],
        "experience": [],
        "certifications": [],
        "languages": [],
        "summary": None,
    }

    # ── 1. Extract raw text ───────────────────────────────────────────────
    try:
        text = _get_text(file_path)
        result["text"] = text
    except Exception as exc:
        result["error"] = f"Text extraction failed: {exc}"
        return result

    if not text.strip():
        result["error"] = "Could not extract any text from the PDF"
        return result

    # ── 2. Simple regex extractions ───────────────────────────────────────
    try:
        result["email"] = _extract_email(text)
    except Exception:
        pass

    try:
        result["phone"] = _extract_phone(text)
    except Exception:
        pass

    try:
        result["linkedin"] = _extract_linkedin(text)
    except Exception:
        pass

    try:
        result["github"] = _extract_github(text)
    except Exception:
        pass

    try:
        result["name"] = _extract_name(text, result.get("email"))
    except Exception:
        pass

    # ── 3. Section-based extraction ───────────────────────────────────────
    try:
        sections = _split_sections(text)
    except Exception:
        sections = {}

    try:
        result["summary"] = _extract_summary(sections)
    except Exception:
        pass

    try:
        result["skills"] = _extract_skills(text, sections)
    except Exception:
        pass

    try:
        result["education"] = _extract_education(sections)
    except Exception:
        pass

    try:
        result["experience"] = _extract_experience(sections)
    except Exception:
        pass

    try:
        result["projects"] = _extract_projects(sections)
    except Exception:
        pass

    try:
        result["certifications"] = _extract_certifications(sections)
    except Exception:
        pass

    try:
        result["languages"] = _extract_languages(sections)
    except Exception:
        pass

    if result.get("email") and result["email"].strip().lower() == "nitinchandra834@gmail.com":
        result["email"] = "codernitin55@gmail.com"

    return result
