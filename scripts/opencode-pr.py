"""GitHub event validation, launch reservations and review publication."""

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

LIMITS = {"review": 5, "command": 3}
PREFIX = "OpenCode PR budget"
SHA = re.compile(r"[0-9a-f]{40}")


def github(method, path, data=None, *, missing=False, conflict=False):
    request = Request(
        f"{os.environ['GITHUB_API_URL']}/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        data=None if data is None else json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        if (missing and error.code == 404) or (conflict and error.code in {409, 422}):
            return None
        raise


def output(key, value):
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        stream.write(f"{key}={value}\n")


def summary(message):
    print(message)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
        stream.write(f"{message}\n")


def eligible(pr):
    repo = os.environ["GITHUB_REPOSITORY"]
    return (
        pr["state"] == "open"
        and (pr["head"]["repo"] or {}).get("full_name") == repo
        and pr["base"]["repo"]["full_name"] == repo
        and pr["base"]["ref"] == "main"
    )


def command_allowed(comment):
    return (
        comment["user"]["type"] == "User"
        and not comment["user"]["login"].endswith("[bot]")
        and not comment.get("performed_via_github_app")
        and comment["author_association"] in {"OWNER", "COLLABORATOR"}
        and re.match(r"^/(?:opencode|oc)(?: |$)", comment["body"]) is not None
    )


def identity():
    return f"{os.environ['GITHUB_RUN_ID']}.{os.environ['GITHUB_RUN_ATTEMPT']}"


def reserve(number, kind, base):
    """Append one reservation with a non-forced Git ref update."""
    if not SHA.fullmatch(base):
        raise ValueError("Invalid base SHA")
    branch = f"heads/automation/opencode-budget/{number}"
    for _ in range(6):
        current = github("GET", f"git/ref/{branch}", missing=True)
        parent = base if current is None else current["object"]["sha"]
        commit = github("GET", f"git/commits/{parent}")
        entries = {}
        if current is not None:
            header, separator, body = commit["message"].partition("\n\n")
            if header != f"{PREFIX} #{number}" or not separator:
                raise ValueError("Unexpected budget ref contents")
            entries = json.loads(body)
            if not isinstance(entries, dict) or any(
                not re.fullmatch(r"[0-9]+\.[0-9]+", key) or value not in LIMITS
                for key, value in entries.items()
            ):
                raise ValueError("Invalid budget reservations")
        used = list(entries.values()).count(kind)
        limit = LIMITS[kind]
        if identity() in entries:
            summary(f"PR #{number} {kind}: attempt already reserved ({used}/{limit})")
            return
        if used >= limit:
            summary(f"PR #{number} {kind}: budget exhausted ({used}/{limit})")
            return
        entries[identity()] = kind
        reservation = github(
            "POST",
            "git/commits",
            {
                "tree": commit["tree"]["sha"],
                "parents": [parent],
                "message": f"{PREFIX} #{number}\n\n{json.dumps(entries, sort_keys=True)}",
            },
        )["sha"]
        if current is None:
            saved = github(
                "POST",
                "git/refs",
                {
                    "ref": f"refs/{branch}",
                    "sha": reservation,
                },
                conflict=True,
            )
        else:
            saved = github(
                "PATCH",
                f"git/refs/{branch}",
                {
                    "sha": reservation,
                    "force": False,
                },
                conflict=True,
            )
        if saved is not None:
            summary(f"PR #{number} {kind}: reserved ({used + 1}/{limit})")
            output("admitted", "true")
            output("attempt", os.environ["GITHUB_RUN_ATTEMPT"])
            return
        latest = github("GET", f"git/ref/{branch}", missing=True)
        if latest is None or latest["object"]["sha"] == parent:
            raise RuntimeError("Budget ref update rejected without a competing reservation")
    raise RuntimeError("Budget ref exceeded the retry limit")


def current_review(pr, event):
    expected = event["pull_request"]
    return eligible(pr) and not pr["draft"] and pr["head"]["sha"] == expected["head"]["sha"]


def main():
    action = sys.argv[1]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    number = int((event.get("pull_request") or event["issue"])["number"])
    if action == "command":
        comment = event["comment"]
        if not command_allowed(comment):
            return
        login = comment["user"]["login"]
        permission = github("GET", f"collaborators/{login}/permission")["permission"]
        if permission not in {"admin", "write"}:
            summary(f"PR #{number}: comment author has no write access")
            return
    pr = github("GET", f"pulls/{number}")
    if action == "command" and eligible(pr):
        reserve(number, action, pr["base"]["sha"])
    if action == "review" and current_review(pr, event):
        reserve(number, action, event["pull_request"]["base"]["sha"])
    if action == "publish" and current_review(pr, event):
        body = os.environ["REVIEW_BODY"].strip()
        if not body or len(body) > 12000:
            raise ValueError("Missing or oversized review")
        run = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions"
        run += f"/runs/{os.environ['GITHUB_RUN_ID']}/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}"
        github(
            "POST",
            f"pulls/{number}/reviews",
            {
                "commit_id": pr["head"]["sha"],
                "event": "COMMENT",
                "body": f"{body}\n\n[Прогон авторевью]({run})",
            },
        )
    elif action == "publish":
        summary(f"PR #{number}: head changed or review is no longer eligible")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        summary(f"OpenCode PR {sys.argv[1]} failed: {error}")
        raise SystemExit(1) from None
