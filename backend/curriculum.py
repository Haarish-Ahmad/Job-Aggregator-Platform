"""Load and validate curriculum.yaml."""
from pathlib import Path

import yaml


def load_curriculum(path: Path) -> list[dict]:
    """Courses as [{"name": str, "skills": [lowercase str]}]. Raises ValueError with a readable message."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"curriculum file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"curriculum file is not valid YAML: {exc}") from exc
    courses = (data or {}).get("courses") if isinstance(data, dict) else None
    if not isinstance(courses, list) or not courses:
        raise ValueError("curriculum file needs a non-empty 'courses' list")
    result = []
    for i, course in enumerate(courses, start=1):
        name = course.get("name") if isinstance(course, dict) else None
        skills = course.get("skills") if isinstance(course, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"course #{i} needs a 'name'")
        if not isinstance(skills, list) or not skills or not all(isinstance(s, (str, int, float)) for s in skills):
            raise ValueError(f"course '{name}' needs a non-empty 'skills' list")
        result.append({"name": name.strip(), "skills": sorted({str(s).strip().lower() for s in skills if str(s).strip()})})
    return result
