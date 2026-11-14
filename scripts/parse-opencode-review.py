"""Validate text output from the independent OpenCode review."""

import json
import os
import sys
from pathlib import Path

parts = []
for line in sys.stdin:
    event = json.loads(line)
    if event["type"] == "error":
        raise SystemExit("OpenCode reported an error. Check the provider configuration.")
    if event["type"] == "text":
        parts.append(event["part"]["text"])

try:
    result = json.loads("".join(parts))
except ValueError:
    raise SystemExit("OpenCode did not return the expected review JSON.") from None
body = result.get("body") if isinstance(result, dict) else None
if not isinstance(body, str) or not body.strip() or len(body) > 12000:
    raise SystemExit("OpenCode returned an empty or oversized review.")
# Encode newlines in the job output without allowing the model to define outputs.
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
    stream.write("body=" + json.dumps(body, ensure_ascii=False) + "\n")
