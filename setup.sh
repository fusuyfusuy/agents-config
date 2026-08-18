#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --------------------------------------------------------------------------
# agent detection & selection
# --------------------------------------------------------------------------

detect_agents() {
    HAVE_CLAUDE=false; HAVE_AGY=false; HAVE_PI=false

    if command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ]; then HAVE_CLAUDE=true; fi
    if command -v agy    >/dev/null 2>&1 || [ -d "$HOME/.gemini" ]; then HAVE_AGY=true; fi
    if command -v pi     >/dev/null 2>&1 || [ -d "$HOME/.pi" ];     then HAVE_PI=true; fi
}

state() { [ "$1" = true ] && echo "installed" || echo "not found"; }

# Map a selection string ('cap', 'all', 'none', ...) onto the install flags.
# 'all' installs whatever was detected; an explicit letter set installs exactly those.
resolve_selection() {
    local sel
    sel=$(echo "${1:-all}" | tr '[:upper:]' '[:lower:]')

    INSTALL_CLAUDE=false; INSTALL_AGY=false; INSTALL_PI=false
    case "$sel" in
        all)  INSTALL_CLAUDE=$HAVE_CLAUDE; INSTALL_AGY=$HAVE_AGY; INSTALL_PI=$HAVE_PI ;;
        none) : ;;
        *)    [[ "$sel" == *c* ]] && INSTALL_CLAUDE=true
              [[ "$sel" == *a* ]] && INSTALL_AGY=true
              [[ "$sel" == *p* ]] && INSTALL_PI=true ;;
    esac
}

choose_agents() {
    echo "==> Detected agents:"
    printf "    [c] Claude Code              : %s\n" "$(state "$HAVE_CLAUDE")"
    printf "    [a] AGY (Antigravity/Gemini)  : %s\n" "$(state "$HAVE_AGY")"
    printf "    [p] pi                       : %s\n" "$(state "$HAVE_PI")"
    echo

    # Non-interactive override for automation/CI: AGENTS='cap' | 'all' | 'none' | letters.
    if [ -n "${AGENTS:-}" ]; then
        echo "==> AGENTS override: installing for '$AGENTS'."
        resolve_selection "$AGENTS"
        return
    fi

    # Non-interactive (piped/CI): configure everything that is installed, never hang on read.
    if [ ! -t 0 ]; then
        INSTALL_CLAUDE=$HAVE_CLAUDE; INSTALL_AGY=$HAVE_AGY; INSTALL_PI=$HAVE_PI
        echo "==> Non-interactive shell: installing for all detected agents."
        return
    fi

    echo "Which agents should I configure here?"
    echo "  Enter letters to select (e.g. 'cap'), 'all', 'none', or leave blank for all detected:"
    read -r sel
    resolve_selection "${sel:-all}"
}

# --------------------------------------------------------------------------
# linking
# --------------------------------------------------------------------------

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

# Fan out the shared skills (canonical source: claude/skills) into an agent's
# global skill directory. Same source, three targets.
link_skills() {
    local dest_root="$1"
    mkdir -p "$dest_root"
    if [ -d "$SCRIPT_DIR/claude/skills" ]; then
        find "$SCRIPT_DIR/claude/skills" -type f | sort | while read -r skill_file; do
            rel_path="${skill_file#$SCRIPT_DIR/claude/skills/}"
            link_file "$skill_file" "$dest_root/$rel_path"
        done
    fi
}

# --------------------------------------------------------------------------
# per-agent install
# --------------------------------------------------------------------------

install_shared() {
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
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-quotas/scripts/helpers.sh" \
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert/tmux-agent-alert.tmux" \
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert/scripts/alert_handler.sh" \
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert/scripts/render_alerts.sh" \
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert/scripts/clear_alert.sh" \
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert/scripts/jump_to_alert.sh" \
             "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert/scripts/helpers.sh"

    mkdir -p "$HOME/.local/bin"

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
    if [ -d "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert" ]; then
        ln -sfn "$SCRIPT_DIR/tmux/plugins/tmux-agent-alert" "$HOME/.tmux/plugins/tmux-agent-alert"
        echo "  [LINK] Linked tmux plugin: $HOME/.tmux/plugins/tmux-agent-alert"
    fi
}

install_claude() {
    echo "==> Configuring Claude Code..."
    link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.claude/CLAUDE.md"
    link_file "$SCRIPT_DIR/claude/settings.json"             "$HOME/.claude/settings.json"
    link_file "$SCRIPT_DIR/claude/statusline-command.sh"     "$HOME/.claude/statusline-command.sh"
    link_skills "$HOME/.claude/skills"
}

install_agy() {
    echo "==> Configuring AGY (Antigravity / Gemini)..."
    mkdir -p "$HOME/.gemini/antigravity-cli" "$HOME/.gemini/config/skills" "$HOME/.antigravity"

    # Shared rules
    link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.gemini/AGENTS.md"

    # Antigravity & Gemini CLI
    link_file "$SCRIPT_DIR/antigravity-cli/settings.json"    "$HOME/.gemini/antigravity-cli/settings.json"
    link_file "$SCRIPT_DIR/antigravity-cli/keybindings.json" "$HOME/.gemini/antigravity-cli/keybindings.json"
    link_file "$SCRIPT_DIR/config/config.json"               "$HOME/.gemini/config/config.json"
    link_file "$SCRIPT_DIR/config/mcp_config.json"           "$HOME/.gemini/config/mcp_config.json"
    link_file "$SCRIPT_DIR/status/statusline.sh"            "$HOME/.gemini/antigravity-cli/statusline.sh"
    link_file "$SCRIPT_DIR/status/status.py"                 "$HOME/.antigravity/status.py"
    link_file "$SCRIPT_DIR/status/agy-quota-cache.py"        "$HOME/.antigravity/agy-quota-cache.py"

    link_skills "$HOME/.gemini/config/skills"
}

install_pi() {
    echo "==> Configuring pi..."
    mkdir -p "$HOME/.pi/agent/skills"

    # Global instructions
    link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.pi/agent/AGENTS.md"

    # Skills (directories with SKILL.md) are discovered from ~/.pi/agent/skills/
    link_skills "$HOME/.pi/agent/skills"
}

# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

detect_agents
choose_agents

install_shared
if [ "$INSTALL_CLAUDE" = true ]; then install_claude; fi
if [ "$INSTALL_AGY"    = true ]; then install_agy; fi
if [ "$INSTALL_PI"     = true ]; then install_pi; fi

echo "==> Setup completed successfully!"
