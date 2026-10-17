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
repository=aryanraj2713/pyngrok

# A previous attempt may have created the repository before its push failed.
if visibility=$(gh repo view "$repository" --json visibility --jq .visibility); then
  if [ "$visibility" != PUBLIC ]; then
    echo "Refusing to publish: $repository exists but is not public." >&2
    exit 1
  fi
else
  gh repo create "$repository" --public \
    --description "Typed Python CLI and Rust reverse-tunnel engine with a terminal dashboard"
fi

git clone "$bundle" "$checkout"
git -C "$checkout" remote set-url origin "https://github.com/$repository.git"
echo "Publishing checkout: $checkout"
push_log="$publish_workspace/push.log"
if git -C "$checkout" push --set-upstream origin main >"$push_log" 2>&1; then
  cat "$push_log"
  echo "Published: https://github.com/$repository"
else
  cat "$push_log" >&2
  if grep -q 'without.*workflow.*scope' "$push_log"; then
    echo "Grant GitHub Actions permission, then rerun this script:" >&2
    echo "  gh auth refresh --hostname github.com --scopes workflow" >&2
    echo "  $project_root/scripts/publish-github.sh" >&2
  fi
  exit 1
fi
