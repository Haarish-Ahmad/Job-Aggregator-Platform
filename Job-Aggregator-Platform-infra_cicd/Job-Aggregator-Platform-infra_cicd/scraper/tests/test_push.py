"""Mapping scraped records onto the backend schema, and sending them."""
import json
from datetime import UTC, date, datetime

import httpx
import pytest

from scraper.config import Settings
from scraper.models import EmploymentType, JobRecord, WorkMode
from scraper.push import (
    MAX_LOCATION,
    BackendPusher,
    clean_skill_list,
    india_flag,
    is_remote,
    join_locations,
    to_payload,
)
from scraper.storage.jsonl import JsonlStorage


def record(**kw) -> JobRecord:
    base = dict(source="shine", company="Acme", external_id="42", url="https://www.shine.com/jobs/x/acme/42",
                scraped_at=datetime.now(UTC), content_hash="h" * 64, title="Software Developer (Fresher)",
                employment_type=EmploymentType.full_time, locations=["Bangalore"], description_text="Build things.",
                required_qualifications=["Python", "SQL"])
    return JobRecord(**{**base, **kw})


# --- locations
def test_short_locations_are_joined_and_deduplicated():
    assert join_locations(["Pune", "Mumbai", "pune ", "Pune"]) == "Pune, Mumbai, pune"
    assert join_locations([]) is None and join_locations(["", "  "]) is None


def test_long_location_lists_are_cut_with_a_count():
    places = [f"City Number {i}" for i in range(40)]
    out = join_locations(places)
    assert len(out) <= MAX_LOCATION and out.startswith("City Number 0, City Number 1")
    kept = out.count("City Number")
    assert out.endswith(f", +{40 - kept} more")


def test_a_single_enormous_place_is_truncated():
    out = join_locations(["Word " * 100])
    assert len(out) <= MAX_LOCATION and out.endswith("…")


# --- skills
def test_requirement_sentences_are_not_skills():
    items = ["Python", "Bachelor's degree in Computer Science", "3+ years of experience with Java",
             "Strong communication skills", "REST APIs", "python", "Ability to work in a team.", "x", "Problem Solving"]
    assert clean_skill_list(items) == ["python", "rest apis", "problem solving"]


def test_skill_list_is_capped():
    assert len(clean_skill_list([f"Skill{i}" for i in range(100)])) == 30


# --- payload
def test_payload_maps_the_fields():
    p = to_payload(record(posted_date=date(2026, 10, 1), overview="Salary: 3 LPA"), india_portal=True)
    assert p["company_name"] == "Acme" and p["title"] == "Software Developer (Fresher)"
    assert p["apply_url"].endswith("/42") and p["source"] == "shine" and p["external_id"] == "42"
    assert len(p["source_content_hash"]) == 64 and p["job_type"] == "full_time" and p["posted_date"] == "2026-10-01"
    assert p["description"] == "Salary: 3 LPA\n\nBuild things." and p["required_skills"] == ["python", "sql"]
    assert p["is_india"] is True and p["is_remote"] is False


def test_unknown_employment_type_is_omitted():
    assert to_payload(record(employment_type=EmploymentType.unknown))["job_type"] is None


def test_skills_are_read_from_the_text_when_the_source_lists_only_sentences():
    sentences = ["Bachelor's degree in Computer Science or a related field", "2+ years of experience building services"]
    p = to_payload(record(required_qualifications=sentences, title="Software Engineer",
                          description_text="You will build services in Python on Azure with Kubernetes."))
    assert p["required_skills"] == ["python", "azure", "kubernetes"]


def test_the_sources_own_skills_come_before_the_text_search():
    assert to_payload(record(description_text="Uses Docker and Java."))["required_skills"] == ["python", "sql"]


def test_a_posting_that_names_nothing_has_no_skills():
    p = to_payload(record(required_qualifications=["Strong communication skills"], description_text="Join our friendly team."))
    assert p["required_skills"] == []


def test_values_are_cut_to_the_backend_limits():
    p = to_payload(record(company="C" * 300, title="T " * 300, locations=["L" * 400], external_id="9"))
    assert len(p["company_name"]) <= 100 and len(p["title"]) <= 255 and len(p["location"]) <= 150
    assert p["company_name"].endswith("…")


def test_long_urls_lose_their_query_string_or_the_record_is_dropped():
    long_query = "https://x.com/job/1?" + "a=1&" * 200
    assert to_payload(record(url=long_query))["apply_url"] == "https://x.com/job/1"
    assert to_payload(record(url="https://x.com/" + "p" * 600)) is None


def test_records_without_a_company_or_title_cannot_be_mapped():
    assert to_payload(record(company="  ")) is None and to_payload(record(title="")) is None


# --- remote / india flags
@pytest.mark.parametrize("kw,expected", [
    ({"locations": ["Work from home"]}, True), ({"locations": ["Remote - India"]}, True), ({"title": "Dev (WFH)"}, True),
    ({"work_mode": WorkMode.remote}, True), ({"locations": ["Pune"]}, False),
])
def test_remote_detection(kw, expected):
    assert is_remote(record(**kw)) is expected


@pytest.mark.parametrize("locations,portal,expected", [
    (["Pune"], False, True), (["Mumbai City"], False, True), (["All India"], False, True),
    (["Vadodara"], False, True), (["Tiny Village"], False, False), (["Tiny Village"], True, True),
    (["Austin, TX, US"], False, False), (["London, United Kingdom"], True, False),
    (["Work from home"], True, None), ([], True, None), (["Remote"], False, None),
    (["Bangalore, Karnataka, India", "Singapore"], False, True),
])
def test_india_flag(locations, portal, expected):
    assert india_flag(record(locations=locations), portal) is expected


# --- pusher
class FakeBackend:
    """Stands in for POST /internal/jobs; records requests, answers like the real endpoint."""

    def __init__(self, behaviour=None):
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.behaviour = behaviour or self.ok

    @staticmethod
    def ok(request, body):
        return httpx.Response(200, json={"results": [{"index": i, "status": "inserted", "job_id": i + 1} for i, _ in enumerate(body["jobs"])]})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(dict(request.headers))
        return self.behaviour(request, body)

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="http://backend", transport=httpx.MockTransport(self))


@pytest.fixture
def settings(tmp_path):
    return Settings(ingest_token="secret-token", ingest_batch_size=3, output_dir=tmp_path)


def make_pusher(settings, tmp_path, backend):
    return BackendPusher(settings, JsonlStorage(tmp_path), client=backend.client(), india_portal=True)


def failures(tmp_path):
    path = tmp_path / "dead_letter.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_records_are_sent_in_batches_with_the_token(settings, tmp_path):
    backend = FakeBackend()
    pusher = make_pusher(settings, tmp_path, backend)
    for i in range(7):
        pusher.add(record(external_id=str(i)))
    stats = pusher.flush()
    assert [len(r["jobs"]) for r in backend.requests] == [3, 3, 1] and stats.inserted == 7
    assert backend.headers[0]["x-ingest-token"] == "secret-token"


def test_backend_answers_are_counted(settings, tmp_path):
    def mixed(request, body):
        statuses = ["inserted", "updated", "unchanged", "rejected"]
        return httpx.Response(200, json={"results": [
            {"index": i, "status": statuses[i % 4], "reason": "location too long (200 > 150)" if i % 4 == 3 else None}
            for i, _ in enumerate(body["jobs"])]})

    backend = FakeBackend(mixed)
    pusher = make_pusher(Settings(ingest_token="t", ingest_batch_size=4, output_dir=tmp_path), tmp_path, backend)
    for i in range(4):
        pusher.add(record(external_id=str(i)))
    s = pusher.flush()
    assert (s.inserted, s.updated, s.unchanged, s.rejected) == (1, 1, 1, 1)
    assert s.reasons == {"location too long": 1}
    assert [f["stage"] for f in failures(tmp_path)] == ["ingest"] and "location too long" in failures(tmp_path)[0]["error"]


def test_an_unmappable_record_is_dropped_and_logged_not_sent(settings, tmp_path):
    backend = FakeBackend()
    pusher = make_pusher(settings, tmp_path, backend)
    pusher.add(record(company=" "))
    pusher.add(record(external_id="ok"))
    s = pusher.flush()
    assert s.dropped == 1 and s.inserted == 1 and len(backend.requests[0]["jobs"]) == 1
    assert len(failures(tmp_path)) == 1


def test_a_refused_token_stops_further_attempts(settings, tmp_path):
    backend = FakeBackend(lambda r, b: httpx.Response(401, json={"detail": "Invalid ingest token"}))
    pusher = make_pusher(settings, tmp_path, backend)
    for i in range(7):
        pusher.add(record(external_id=str(i)))
    s = pusher.flush()
    assert s.failed == 7 and s.inserted == 0
    assert len(backend.requests) == 1  # the first batch found out; the rest were not even tried
    assert "INGEST_TOKEN" in failures(tmp_path)[0]["error"]


def test_server_errors_are_retried(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(request, body):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else FakeBackend.ok(request, body)

    backend = FakeBackend(flaky)
    pusher = make_pusher(settings, tmp_path, backend)
    pusher.add(record())
    s = pusher.flush()
    assert calls["n"] == 3 and s.inserted == 1 and s.failed == 0


def test_an_unreachable_backend_fails_records_without_raising(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda s: None)

    def down(request, body):
        raise httpx.ConnectError("connection refused")

    pusher = make_pusher(settings, tmp_path, FakeBackend(down))
    pusher.add(record())
    s = pusher.flush()
    assert s.failed == 1 and "ConnectError" in failures(tmp_path)[0]["error"]


def test_a_422_batch_is_split_to_find_the_bad_record(settings, tmp_path):
    def picky(request, body):
        if len(body["jobs"]) > 1 and any(j["external_id"] == "bad" for j in body["jobs"]):
            return httpx.Response(422, json={"detail": "bad"})
        if body["jobs"][0]["external_id"] == "bad":
            return httpx.Response(422, json={"detail": "bad"})
        return FakeBackend.ok(request, body)

    backend = FakeBackend(picky)
    pusher = make_pusher(settings, tmp_path, backend)
    for ext in ("a", "bad", "b"):
        pusher.add(record(external_id=ext))
    s = pusher.flush()
    assert s.inserted == 2 and s.rejected == 1


def test_flush_with_nothing_buffered_sends_nothing(settings, tmp_path):
    backend = FakeBackend()
    make_pusher(settings, tmp_path, backend).flush()
    assert backend.requests == []


# --- the fingerprint the backend compares
def fingerprint(**kw):
    return to_payload(record(**kw))["source_content_hash"]


def test_fingerprint_is_stable_for_the_same_record():
    assert fingerprint() == fingerprint()


def test_fingerprint_changes_when_anything_sent_changes():
    base = fingerprint()
    changed = [fingerprint(company="Other Co"), fingerprint(title="New title"), fingerprint(locations=["Pune"]),
               fingerprint(description_text="different text"), fingerprint(required_qualifications=["Go"]),
               fingerprint(posted_date=date(2026, 10, 1)), fingerprint(url="https://www.shine.com/jobs/x/acme/43")]
    assert base not in changed and len(set(changed)) == len(changed)


def test_fingerprint_ignores_what_is_not_sent():
    assert fingerprint(content_hash="a" * 64) == fingerprint(content_hash="b" * 64)
