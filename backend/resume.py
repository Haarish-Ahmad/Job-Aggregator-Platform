import re
import io
from sqlalchemy import text
from pypdf import PdfReader
SEED = {
    "python", "java", "javascript", "typescript", "sql", "postgresql", "mongodb",
    "react", "vue", "node.js", "fastapi", "flask", "django", "docker", "git", "sqlite",
    "aws", "linux", "c++", "c#", "machine learning", "deep learning", "pandas",
    "numpy", "pytorch", "tensorflow", "html", "css", "tailwind", "rest api","sckit-learn","langchain","langgraph","chromadb","faiss","computer networks","networking",
    "crewai","aws","azure","jenkins","github actions","devops","kali","metasploit","operating systems","object oriented programming","go","kotlin","react-native"
}
ALIASES = {
    "js": "javascript", "ts": "typescript", "postgres": "postgresql","os":"operating systems",
    "ml": "machine learning", "dl": "deep learning", "nodejs": "node.js",
}

CGPA_RE=re.compile(r"(?:cgpa|gpa)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)(?![\d.])(?!\s*/\s*4)", re.I)
def pdf_to_text(data: bytes, max_pages: int = 5)->str:
    reader=PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])

def load_vocab(db) -> set[str]:
    rows = db.execute(text(
        "SELECT DISTINCT lower(trim(s)) FROM job_postings, unnest(necessary_skills) s "
        "WHERE trim(s) <> ''"
    )).scalars().all()
    return SEED|{r for r in rows if len(r)>=2}

def _has(term: str, t: str)->bool:
    return re.search(rf"(?<![a-z0-9+#.]){re.escape(term)}(?![a-z0-9+#])",t) is not None

def extract_skills(raw:str,vocab: set[str])->list[str]:
    t = raw.lower()
    found = {s for s in vocab if _has(s, t)}
    found |= {canon for alias, canon in ALIASES.items() if _has(alias, t)}
    return sorted(found)

def extract_cgpa(raw: str) -> float | None:
    m=CGPA_RE.search(raw)
    if m and 0 < float(m.group(1)) <= 10:
        return float(m.group(1))
    return None

def extract_grad_year(raw: str) -> int | None:
    years=[int(y) for y in re.findall(r"\b(20[2-3]\d)\b",raw) if 2024 <= int(y) <= 2035]
    return max(years) if years else None
