"""Keyword skill finder: names the technologies a posting asks for by searching its text.

Used when a source gives no usable skill list (Microsoft, Google and Greenhouse list requirement sentences, not
skills). A posting names what it needs, so finding a name in the text is enough; no model is involved.

Matching is whole-word and case-insensitive: "java" does not match "javascript", and a name that is also an
everyday word ("go", "r", "c", "spring", "express", "oracle") is only listed in an unambiguous form
("golang", "spring boot", "express.js", "oracle database"). Names follow backend/curriculum.yaml where they overlap,
so the curriculum report can count them.
"""
import re

# canonical (lower-case) name -> other spellings that mean the same skill. The canonical name is always accepted.
SKILLS: dict[str, tuple[str, ...]] = {
    # languages
    "python": (),
    "java": (),
    "javascript": ("js", "ecmascript"),
    "typescript": (),
    "c++": ("cpp",),
    "c#": ("csharp", "c sharp"),
    "golang": (),
    "rust": (),
    "kotlin": (),
    "php": (),
    "ruby": (),
    "scala": (),
    "matlab": (),
    "sql": (),
    "shell scripting": ("bash", "shell script", "bash scripting"),
    "html": ("html5",),
    "css": ("css3",),
    # web and app frameworks
    "react": ("react.js", "reactjs"),
    "angular": ("angularjs",),
    "vue": ("vue.js", "vuejs"),
    "node.js": ("nodejs", "node"),
    "express.js": ("expressjs",),
    "django": (),
    "flask": (),
    "fastapi": (),
    "spring boot": ("springboot",),
    ".net": ("dotnet", "asp.net"),
    "rest api": ("rest apis", "restful api", "restful apis", "restful"),  # not bare "rest": "the rest of the team"
    "graphql": (),
    "microservices": ("microservice",),
    # data and machine learning
    "machine learning": ("ml",),
    "deep learning": (),
    "nlp": ("natural language processing",),
    "computer vision": (),
    "pandas": (),
    "numpy": (),
    "scikit-learn": ("sklearn", "scikit learn"),
    "tensorflow": (),
    "pytorch": (),
    "keras": (),
    "spark": ("apache spark", "pyspark"),
    "hadoop": (),
    "kafka": ("apache kafka",),
    "airflow": ("apache airflow",),
    "power bi": ("powerbi",),
    "tableau": (),
    "excel": ("ms excel", "microsoft excel"),
    # databases
    "mysql": (),
    "postgresql": ("postgres",),
    "mongodb": ("mongo",),
    "redis": (),
    "sqlite": (),
    "nosql": (),
    "dynamodb": (),
    "elasticsearch": ("elastic search",),
    "oracle database": ("oracle sql", "oracle db"),
    # cloud and devops
    "aws": ("amazon web services",),
    "azure": ("microsoft azure",),
    "gcp": ("google cloud", "google cloud platform"),
    "docker": (),
    "kubernetes": ("k8s",),
    "terraform": (),
    "ansible": (),
    "jenkins": (),
    "ci/cd": ("cicd", "ci cd"),
    "github actions": (),
    "linux": (),
    "git": (),
    "github": (),
    "gitlab": (),
    "jira": (),
    # engineering practice
    "data structures": ("data structure",),
    "algorithms": ("algorithm",),
    "oop": ("object oriented programming", "object-oriented programming", "object oriented", "object-oriented"),
    "design patterns": ("design pattern",),
    "agile": (),
    "scrum": (),
    "testing": (),
    "software testing": (),
    "selenium": (),
    "networking": ("computer networks", "computer networking"),
    # security
    "cybersecurity": ("cyber security", "information security"),
    "penetration testing": ("pentesting", "pen testing"),
    "ethical hacking": (),
}

# A name is a whole word when it is not glued to a letter, digit, "_" or the symbols that belong to names
# (so "c++" is not "c", "node.js" is not "js", and "java" is not inside "javascript").
_BEFORE = r"(?<![\w.+#])"
_AFTER = r"(?![\w+#])"


def _compile(name: str, aliases: tuple[str, ...]) -> re.Pattern[str]:
    spellings = sorted({name, *aliases}, key=len, reverse=True)  # longest first, so "rest apis" beats "rest"
    return re.compile(_BEFORE + "(?:" + "|".join(re.escape(s) for s in spellings) + ")" + _AFTER, re.IGNORECASE)


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [(name, _compile(name, aliases)) for name, aliases in SKILLS.items()]


def extract_skills(text: str) -> list[str]:
    """The skills named in `text`, in the order of SKILLS, each once."""
    if not text:
        return []
    return [name for name, pattern in _PATTERNS if pattern.search(text)]
