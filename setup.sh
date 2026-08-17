#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Setting up Antigravity / Gemini / Claude agents-config symlinks..."

# Ensure base target directories exist
mkdir -p "$HOME/.gemini/antigravity-cli"
mkdir -p "$HOME/.gemini/config/skills"
mkdir -p "$HOME/.antigravity"
mkdir -p "$HOME/.claude/skills"
mkdir -p "$HOME/.local/bin"

# Set executable permissions on scripts
chmod +x "$SCRIPT_DIR/setup.sh" \
         "$SCRIPT_DIR/bin/agent-ctx" \
         "$SCRIPT_DIR/status/status.py" \
         "$SCRIPT_DIR/status/statusline.sh" \
         "$SCRIPT_DIR/status/agy-quota-cache.py" \
         "$SCRIPT_DIR/claude/statusline-command.sh" \
         "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas/tmux-agent-quotas.tmux" \
         "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas/scripts/render_status.sh" \
         "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas/scripts/fetch_quotas.py" \
         "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas/scripts/helpers.sh"

link_file() {
    local src="$1"
    local dest="$2"

    mkdir -p "$(dirname "$dest")"

    if [ -L "$dest" ] && [ "$(readlink -f "$dest")" = "$(readlink -f "$src")" ]; then
        echo "  [OK] Already symlinked: $dest -> $src"
        return 0
    fi

    if [ -e "$dest" ] && [ ! -L "$dest" ]; then
        local backup="${dest}.bak.$(date +%Y%m%d%H%M%S)"
        echo "  [BACKUP] Existing file backed up to $backup"
        mv "$dest" "$backup"
    fi

    ln -sfn "$src" "$dest"
    echo "  [LINK] Created symlink: $dest -> $src"
}

# Shared rules
link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.gemini/AGENTS.md"
link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.claude/CLAUDE.md"

# Antigravity & Gemini CLI
link_file "$SCRIPT_DIR/antigravity-cli/settings.json"    "$HOME/.gemini/antigravity-cli/settings.json"
link_file "$SCRIPT_DIR/antigravity-cli/keybindings.json" "$HOME/.gemini/antigravity-cli/keybindings.json"
link_file "$SCRIPT_DIR/config/config.json"               "$HOME/.gemini/config/config.json"
link_file "$SCRIPT_DIR/config/mcp_config.json"           "$HOME/.gemini/config/mcp_config.json"
link_file "$SCRIPT_DIR/status/statusline.sh"            "$HOME/.gemini/antigravity-cli/statusline.sh"
link_file "$SCRIPT_DIR/status/status.py"                 "$HOME/.antigravity/status.py"
link_file "$SCRIPT_DIR/status/agy-quota-cache.py"        "$HOME/.antigravity/agy-quota-cache.py"

# Claude Code
link_file "$SCRIPT_DIR/claude/settings.json"             "$HOME/.claude/settings.json"
link_file "$SCRIPT_DIR/claude/statusline-command.sh"     "$HOME/.claude/statusline-command.sh"

# CLI Binaries
link_file "$SCRIPT_DIR/bin/agent-ctx"                   "$HOME/.local/bin/agent-ctx"

# agent-kb: build its venv, then symlink the installed console script
AGENT_KB_DIR="$SCRIPT_DIR/bin/agent-kb"
if [ -d "$AGENT_KB_DIR" ]; then
    if command -v uv >/dev/null 2>&1; then
        (cd "$AGENT_KB_DIR" && uv sync --quiet)
    else
        [ -d "$AGENT_KB_DIR/.venv" ] || python3 -m venv "$AGENT_KB_DIR/.venv"
        "$AGENT_KB_DIR/.venv/bin/pip" install --quiet -e "$AGENT_KB_DIR"
    fi
    link_file "$AGENT_KB_DIR/.venv/bin/agent-kb"        "$HOME/.local/bin/agent-kb"
fi

# Tmux Plugins
mkdir -p "$HOME/.tmux/plugins"
if [ -d "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas" ]; then
    ln -sfn "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas" "$HOME/.tmux/plugins/tmux-agent-quotas"
    echo "  [LINK] Linked tmux plugin: $HOME/.tmux/plugins/tmux-agent-quotas"
fi

# Skills (Claude & Gemini / Antigravity Global)
if [ -d "$SCRIPT_DIR/claude/skills" ]; then
    find "$SCRIPT_DIR/claude/skills" -type f | sort | while read -r skill_file; do
        rel_path="${skill_file#$SCRIPT_DIR/claude/skills/}"
        link_file "$skill_file" "$HOME/.claude/skills/$rel_path"
        link_file "$skill_file" "$HOME/.gemini/config/skills/$rel_path"
    done
fi

echo "==> Setup completed successfully!"
