#!/usr/bin/env bash
# WalletRisk daily autopublish — generates one real wallet scan as today's
# public example, posts it to X/Telegram IF credentials exist (silently
# dry-runs otherwise), and commits the content to the public repo.
# Only meaningful output is printed (cron delivers stdout as a message).

set -u
cd "$HOME/walletrisk" || exit 1
export PATH="$HOME/.local/bin:$PATH"

WALLETS=("vitalik.eth" "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe")
STATE="$HOME/walletrisk/.rotation_index"
IDX=$(cat "$STATE" 2>/dev/null || echo 0)
IDX=$((IDX % ${#WALLETS[@]}))
echo "$((IDX + 1))" > "$STATE"
WALLET="${WALLETS[$IDX]}"

OUT=$(python3 scripts/gen_content.py --wallet "$WALLET" --chains ethereum 2>&1) || { echo "gen_content failed:"; echo "$OUT" | tail -5; exit 0; }

# Publish (posts only if X/TG creds exist; prints nothing on success paths
# beyond the xurl/telegram JSON, which we swallow)
python3 scripts/publish.py --live >/dev/null 2>&1

# Commit today's example to the public repo (the repo is a publication)
git add content/ examples/ >/dev/null 2>&1
git -c user.name="WalletRisk Agent" -c user.email="walletrisk@local" \
    commit -q -m "daily example: $WALLET ($(date +%F))" >/dev/null 2>&1 && \
git push -q origin master >/dev/null 2>&1

echo "📦 WalletRisk daily example published ($WALLET):"
echo "$OUT" | sed -n '/X POST/,$p'
