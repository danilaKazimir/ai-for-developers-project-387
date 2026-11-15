import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

script = Path(__file__).resolve().parents[2] / "scripts" / "opencode-monitor.py"
spec = importlib.util.spec_from_file_location("opencode_monitor", script)
assert spec is not None and spec.loader is not None
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)

APP_URL = "https://calendar.example.com"
REPO = "owner/calendar"


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("APP_URL", APP_URL)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_RUN_ID", "100")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return tmp_path


def report(checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": 2, "app_url": APP_URL, "checks": checks}


def test_healthy_and_infrastructure_results_do_not_request_triage(
    state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    healthy = monitor.check("landing", "passed", "Home", "OK")
    infra_error = monitor.check("browser", "error", "Browser", "Chromium unavailable")
    monkeypatch.setattr(monitor, "collect", lambda: report([healthy, infra_error]))
    monkeypatch.setattr(monitor, "issues", lambda: pytest.fail("Unexpected issue lookup"))

    monitor.prepare(state)

    assert "Подтверждённых находок нет" in (state / "agent-output.md").read_text()
    assert not (state / "decision.json").exists()


def test_reports_multiple_findings_and_creates_only_the_new_one_on_repeat(
    state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    known = monitor.check(monitor.STATUS_ID, "failed", "Страница 404", "404 JSON")
    new = monitor.check("home", "failed", "Главная", "Нет заголовка")
    monitor.write_json(state / "report.json", report([known, new]))
    monitor.write_json(
        state / "decision.json",
        [{"id": item["id"], "decision": "new", "text": "Воспроизведено"} for item in [known, new]],
    )
    existing = [
        {
            "number": 28,
            "body": "<!-- opencode-monitor:status-page-content-type -->",
            "html_url": f"https://github.com/{REPO}/issues/28",
            "state": "closed",
        },
        {
            "number": 29,
            "body": "Пример маркера: `<!-- opencode-monitor:home -->`",
            "html_url": f"https://github.com/{REPO}/issues/29",
            "state": "open",
        },
    ]
    monkeypatch.setattr(monitor, "issues", lambda: existing.copy())

    def github(*args: str) -> str:
        if args[:2] == ("repo", "view"):
            return json.dumps({"nameWithOwner": REPO})
        assert args[:2] == ("issue", "create")
        body = Path(args[-1]).read_text()
        assert body.startswith("<!-- opencode-monitor:home -->\n")
        url = f"https://github.com/{REPO}/issues/30"
        existing.append({"number": 30, "body": body, "html_url": url})
        return url

    monkeypatch.setattr(monitor, "gh", github)
    monitor.publish(state)
    monitor.publish(state)

    output = (state / "summary.md").read_text()
    assert len(existing) == 3
    assert output.count("создана задача") == 1
    assert output.count("#28") == 2
    assert "#30" in output


def test_legacy_replay_preserves_bytes_and_marker(
    state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = json.dumps(
        {
            "app_url": APP_URL,
            "health_http_status": 200,
            "health_ok": True,
            "status_page": {
                "url": APP_URL + "/status",
                "expected": "Страница 404",
                "http_status": 404,
                "content_type": "application/json",
            },
        },
        indent=3,
    ).encode()

    def github(*args: str) -> str:
        if args[0] == "api":
            return json.dumps(
                {
                    "path": monitor.WORKFLOW,
                    "head_branch": "main",
                    "head_repository": {"full_name": REPO},
                    "conclusion": "success",
                }
            )
        (Path(args[-1]) / "report.json").write_bytes(original)
        return ""

    monkeypatch.setattr(monitor, "gh", github)
    path = state / "report.json"
    monitor.replay(path, "30")

    assert path.read_bytes() == original
    assert set(monitor.findings(monitor.validate(monitor.read_json(path)))) == {monitor.STATUS_ID}


def test_model_cannot_publish_an_unknown_check() -> None:
    with pytest.raises(ValueError, match="Invalid triage"):
        monitor.decisions(
            [{"id": "unknown", "decision": "new", "text": "Несуществующая находка"}],
            {"known"},
            set(),
        )
