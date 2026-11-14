"""Write the OpenCode Responses provider configuration for an Actions runner."""

import json
import os
import sys
from pathlib import Path

model = os.environ["PROVIDER_MODEL"]
if not model or not os.environ["PROVIDER_BASE_URL"]:
    raise SystemExit("Set OPENCODE_BASE_URL and OPENCODE_MODEL in Actions Variables.")

config = {
    "small_model": f"openai/{model}",
    "provider": {
        "openai": {
            "options": {
                "baseURL": "{env:PROVIDER_BASE_URL}",
                "apiKey": "{env:PROVIDER_API_KEY}",
            },
            "models": {model: {"name": model}},
        },
    },
}
if "--read-only" in sys.argv:
    config["permission"] = {"*": "deny"}
path = Path(os.environ["RUNNER_TEMP"]) / "opencode-provider.json"
path.write_text(json.dumps(config), encoding="utf-8")
with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
    stream.write(f"OPENCODE_CONFIG={path}\n")
