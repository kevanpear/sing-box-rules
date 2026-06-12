#!/bin/bash
# Sync self-maintained domain rule-sets from the private GitHub repo
# kevanpear/sing-box-rules into sing-box's working dir, restart only on change.
set -euo pipefail

REPO="/home/hzl/sing-box-rules"
DEST="/var/lib/sing-box"
export HTTPS_PROXY="http://127.0.0.1:7890"
export HTTP_PROXY="http://127.0.0.1:7890"

cd "$REPO"
git fetch -q origin master
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/master)"

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "rule-sets already up to date ($LOCAL)"
    exit 0
fi

echo "updating rule-sets: $LOCAL -> $REMOTE"
git reset -q --hard origin/master

changed=0
for f in srs/*.srs; do
    name="$(basename "$f")"
    if ! sudo cmp -s "$f" "$DEST/$name" 2>/dev/null; then
        sudo cp "$f" "$DEST/$name"
        sudo chown sing-box:sing-box "$DEST/$name"
        echo "  synced $name"
        changed=1
    fi
done

if [ "$changed" = 1 ]; then
    sudo systemctl restart sing-box
    echo "sing-box restarted with new rule-sets"
else
    echo "repo advanced but no srs file changed"
fi
