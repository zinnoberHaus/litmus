#!/usr/bin/env bash
# Litmus dev setup — only needed when working ON Litmus itself.
#
# END USERS DO NOT NEED THIS. Install Litmus with:
#     pipx install litmus-data
# or  uv tool install litmus-data
# and then run `litmus` in any directory.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

step() { printf "\n\033[1;34m▸ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$*"; }

# ── 1. Python version ──
step "Checking Python version"
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    ok "Python $python_version"
else
    echo "  Python 3.10+ required (got $python_version)." >&2
    exit 1
fi

# ── 2. Virtualenv ──
step "Setting up virtualenv (.venv)"
if [ -d ".venv" ]; then
    ok ".venv already exists — reusing"
else
    python3 -m venv .venv
    ok "Created .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
ok "Activated .venv"

# ── 3. Install ──
step "Installing Litmus + dev extras (this can take a minute)"
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
ok "Installed editable + dev extras"

# Streamlit is optional but used by the sample dashboard.
if ! python -c "import streamlit" 2>/dev/null; then
    pip install --quiet streamlit
    ok "Installed streamlit (for dashboards)"
fi

# ── 4. .env ──
step "Configuring environment"
if [ -f ".env" ]; then
    ok ".env already exists — leaving it alone"
else
    cp .env.example .env
    ok "Created .env from .env.example"
    warn "Edit .env to add your NOTION_API_KEY, LINEAR_API_KEY, ANTHROPIC_API_KEY"
fi

# ── 5. Doctor ──
step "Running doctor"
litmus doctor || true

# ── 6. Next steps ──
cat <<EOF

────────────────────────────────────────────────────────────
Litmus dev environment ready. Next steps:

  1. (Optional) Edit .env to add API keys for Notion / Linear / Anthropic
  2. Run the demo:        litmus demo
  3. Open the dashboard:  litmus dashboard
  4. Talk to the agents:  open this repo in Claude Code, then:
       "@data-architect I need a daily dashboard of <X> for <stakeholder>"

End users get this same flow with one line:
  pipx install litmus-data && cd ~/anywhere && litmus
────────────────────────────────────────────────────────────
EOF
