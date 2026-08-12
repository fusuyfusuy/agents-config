#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Setting up Antigravity / Gemini agents-config symlinks..."

# Ensure target directories exist
mkdir -p "$HOME/.gemini/antigravity-cli"
mkdir -p "$HOME/.gemini/config"
mkdir -p "$HOME/.antigravity"
mkdir -p "$HOME/.claude"

# Set executable permissions on scripts
chmod +x "$SCRIPT_DIR/setup.sh" \
         "$SCRIPT_DIR/status/status.py" \
         "$SCRIPT_DIR/status/statusline.sh" \
         "$SCRIPT_DIR/status/agy-quota-cache.py"

link_file() {
    local src="$1"
    local dest="$2"

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

link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.gemini/AGENTS.md"
link_file "$SCRIPT_DIR/AGENTS.md"                        "$HOME/.claude/CLAUDE.md"
link_file "$SCRIPT_DIR/antigravity-cli/settings.json"    "$HOME/.gemini/antigravity-cli/settings.json"
link_file "$SCRIPT_DIR/antigravity-cli/keybindings.json" "$HOME/.gemini/antigravity-cli/keybindings.json"
link_file "$SCRIPT_DIR/config/config.json"               "$HOME/.gemini/config/config.json"
link_file "$SCRIPT_DIR/config/mcp_config.json"           "$HOME/.gemini/config/mcp_config.json"
link_file "$SCRIPT_DIR/status/statusline.sh"            "$HOME/.gemini/antigravity-cli/statusline.sh"
link_file "$SCRIPT_DIR/status/status.py"                 "$HOME/.antigravity/status.py"
link_file "$SCRIPT_DIR/status/agy-quota-cache.py"        "$HOME/.antigravity/agy-quota-cache.py"

echo "==> Setup completed successfully!"
