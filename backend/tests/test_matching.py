import os
from types import SimpleNamespace

import pytest

os.environ["APP_ENV"] = "dev"

import matching


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, jobs):
        self.jobs = jobs

    def scalars(self, query):
        return FakeScalars(self.jobs)


def job(job_id, title, embedding=None, min_cgpa=None):
    return SimpleNamespace(
        id=job_id,
        title=title,
        description="",
        necessary_skills=[],
        embedding=embedding,
        is_active=True,
        deadline_at=None,
        min_cgpa=min_cgpa,
        allowed_branches=[],
        allowed_grads=[],
    )


def test_similarity_score_maps_normalized_cosine_to_percent():
    assert matching.similarity_score([1.0, 0.0], [1.0, 0.0]) == 100.0
    assert matching.similarity_score([1.0, 0.0], [0.375, 0.0]) == pytest.approx(50.0)
    assert matching.similarity_score([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert matching.similarity_score(None, [1.0, 0.0]) is None


def test_compute_matches_generates_missing_embeddings_and_keeps_eligibility(monkeypatch):
    student = SimpleNamespace(
        id=1,
        skills=["python"],
        branch="CSE",
        cgpa=8.0,
        grad_year=2026,
        embedding=None,
    )
    strong = job(1, "Strong match")
    weak = job(2, "Weak match")
    ineligible = job(3, "High CGPA", min_cgpa=9.0)
    session = FakeSession([strong, weak, ineligible])
    calls = []

    def fake_embed(texts):
        calls.append(texts)
        if texts[0].startswith("Skills:"):
            return [[1.0, 0.0]]
        return [[1.0, 0.0] if "Strong match" in text else [0.375, 0.0] for text in texts]

    monkeypatch.setattr(matching, "embed", fake_embed)

    results = matching.compute_matches(student, session)

    assert [posting.id for posting, _ in results] == [1, 2]
    assert [score for _, score in results] == pytest.approx([100.0, 50.0])
    assert len(calls) == 2
    assert student.embedding == [1.0, 0.0]
    assert strong.embedding == [1.0, 0.0] and weak.embedding == [0.375, 0.0]
    assert ineligible.embedding is None
