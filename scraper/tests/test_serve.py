"""`scraper serve`: scheduling loop, per-source isolation, /metrics and /health."""
import json
import threading
import urllib.request

import httpx

from scraper import serve as serve_module
from scraper.config import Settings
from scraper.pipeline import RunStats
from scraper.push import PushStats
from scraper.serve import ServeState, make_handler, run_cycle, start_status_server


def settings(tmp_path, **kw):
    return Settings(ingest_token="t", output_dir=tmp_path, serve_sources="unstop,shine", metrics_port=0,
                    request_delay_seconds=0, **kw)


def ok_runner(source, settings, client, filters, **kw):
    return RunStats(discovered=5, saved=4), PushStats(inserted=3, unchanged=1), None


def test_cycle_runs_every_source_and_records_results(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(serve_module, "after_cycle", lambda s, c=None: calls.append("after"))
    state = ServeState()

    def runner(source, settings, client, filters, **kw):
        assert kw["push"] is True and kw["extract"] is False and filters.limit == settings.serve_limit
        return ok_runner(source, settings, client, filters)

    run_cycle(settings(tmp_path), state, runner=runner)
    assert set(state.last_results) == {"unstop", "shine"} and state.cycles == 1 and not state.running
    assert state.last_results["unstop"].startswith("ok discovered=5 saved=4") and "inserted=3" in state.last_results["unstop"]
    assert calls == ["after"]


def test_one_failing_source_does_not_stop_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(serve_module, "after_cycle", lambda s, c=None: None)
    state = ServeState()

    def runner(source, *a, **kw):
        if source == "unstop":
            raise RuntimeError("site changed")
        return ok_runner(source, *a)

    run_cycle(settings(tmp_path), state, runner=runner)
    assert state.last_results["unstop"].startswith("error RuntimeError")
    assert state.last_results["shine"].startswith("ok")


def test_no_follow_up_calls_when_nothing_reached_the_backend(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(serve_module, "after_cycle", lambda s, c=None: calls.append(1))
    run_cycle(settings(tmp_path), ServeState(), runner=lambda *a, **kw: (RunStats(), PushStats(failed=3), None))
    assert calls == []


def test_after_cycle_calls_maintenance_then_alerts(tmp_path):
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.url.path, request.headers["x-ingest-token"]))
        return httpx.Response(200, json={})

    client = httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler))
    serve_module.after_cycle(settings(tmp_path), client)
    assert seen == [("/internal/maintenance/deactivate-stale", "t"), ("/internal/alerts/run", "t")]


def test_after_cycle_survives_backend_errors_and_can_skip_alerts(tmp_path):
    def handler(request):
        raise httpx.ConnectError("down")

    client = httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler))
    serve_module.after_cycle(settings(tmp_path, alerts_after_run=False), client)  # does not raise


def test_status_server_serves_metrics_and_health(tmp_path):
    state = ServeState()
    state.last_results["unstop"] = "ok"
    server = start_status_server(state, 0)
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        health = json.load(urllib.request.urlopen(f"{base}/health"))
        assert health["status"] == "ok" and health["last_results"] == {"unstop": "ok"}
        metrics = urllib.request.urlopen(f"{base}/metrics").read().decode()
        assert "scraper_jobs_total" in metrics or "scraper_pages_total" in metrics or "scraper_run_in_progress" in metrics
        try:
            urllib.request.urlopen(f"{base}/nope")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown()


def test_serve_loop_runs_immediately_then_waits_and_stops(tmp_path):
    stop = threading.Event()
    runs = []

    def cycle(settings, state):
        runs.append(1)
        state.cycles += 1
        stop.set()  # stop after the first cycle

    state = serve_module.serve(settings(tmp_path, scrape_interval_hours=1), stop, cycle=cycle)
    assert runs == [1] and state.cycles == 1


def test_serve_can_wait_before_the_first_run(tmp_path):
    stop = threading.Event()
    stop.set()
    runs = []
    serve_module.serve(settings(tmp_path, run_on_start=False), stop, cycle=lambda s, st: runs.append(1))
    assert runs == []


def test_handler_class_is_built_per_state():
    assert make_handler(ServeState()) is not make_handler(ServeState())
