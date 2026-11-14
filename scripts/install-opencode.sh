#!/usr/bin/env bash
set -euo pipefail

archive="$RUNNER_TEMP/opencode-linux-x64-baseline.tar.gz"
install_dir="$RUNNER_TEMP/opencode-bin"
curl --fail --silent --show-error --location --retry 3 \
  https://github.com/anomalyco/opencode/releases/download/v1.19.5/opencode-linux-x64-baseline.tar.gz \
  --output "$archive"
printf '%s  %s\n' '17c200fd4b2289954cc01552559f9b6d03ec157b2ddfb5eb54144f491656333d' "$archive" | sha256sum --check
mkdir -p "$install_dir"
tar -xzf "$archive" -C "$install_dir" opencode
"$install_dir/opencode" --version
printf '%s\n' "$install_dir" >> "$GITHUB_PATH"
