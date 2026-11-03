from pathlib import Path

import main


def test_resume_upload_extracts_profile_data_and_can_be_downloaded(student, monkeypatch, tmp_path: Path):
    content = b"%PDF-1.7 test content"
    monkeypatch.setattr(main.settings, "resume_dir", tmp_path)
    monkeypatch.setattr(main, "pdf_to_text", lambda data: "Python SQL Java CGPA: 8.5 Graduation 2026" * 3)
    monkeypatch.setattr(main, "load_vocab", lambda db: {"python", "sql", "java"})

    response = student.post("/me/resume", files={"file": ("resume.pdf", content, "application/pdf")})

    assert response.status_code == 200
    assert response.json() == {
        "has_resume": True,
        "skills": ["java", "python", "sql"],
        "new_skills": ["java"],
        "cgpa": 8.5,
        "grad_year": 2026,
    }
    assert student.get("/me").json()["has_resume"] is True
    download = student.get("/me/resume")
    assert download.status_code == 200
    assert download.content == content


def test_resume_upload_rejects_non_pdf(student):
    response = student.post("/me/resume", files={"file": ("resume.pdf", b"not a pdf", "application/pdf")})

    assert response.status_code == 415
