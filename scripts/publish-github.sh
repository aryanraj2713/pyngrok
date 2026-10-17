#!/bin/sh
# Publish the prepared commit without modifying this workspace's protected .git.
set -eu

command -v gh >/dev/null 2>&1 || { echo "GitHub CLI (gh) is required." >&2; exit 1; }
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bundle="$project_root/dist/pyngrok.bundle"
if [ ! -f "$bundle" ]; then
  echo "Missing commit bundle: $bundle" >&2
  exit 1
fi

publish_workspace=$(mktemp -d "${TMPDIR:-/tmp}/pyngrok-publish.XXXXXX")
checkout="$publish_workspace/pyngrok"
git clone "$bundle" "$checkout"
git -C "$checkout" remote remove origin
echo "Publishing checkout: $checkout"
gh repo create aryanraj2713/pyngrok --public \
  --description "Typed Python CLI and Rust reverse-tunnel engine with a terminal dashboard" \
  --source "$checkout" --remote origin --push
