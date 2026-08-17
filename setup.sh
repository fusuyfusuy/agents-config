#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Setting up Antigravity / Gemini / Claude agents-config symlinks..."

# Ensure base target directories exist
mkdir -p "$HOME/.gemini/antigravity-cli"
mkdir -p "$HOME/.gemini/config/skills"
mkdir -p "$HOME/.antigravity"
mkdir -p "$HOME/.claude/skills"

# Set executable permissions on scripts
chmod +x "$SCRIPT_DIR/setup.sh" \
         "$SCRIPT_DIR/status/status.py" \
         "$SCRIPT_DIR/status/statusline.sh" \
         "$SCRIPT_DIR/status/agy-quota-cache.py" \
         "$SCRIPT_DIR/claude/statusline-command.sh"

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

# Skills (Claude & Gemini / Antigravity Global)
if [ -d "$SCRIPT_DIR/claude/skills" ]; then
    find "$SCRIPT_DIR/claude/skills" -type f | sort | while read -r skill_file; do
        rel_path="${skill_file#$SCRIPT_DIR/claude/skills/}"
        link_file "$skill_file" "$HOME/.claude/skills/$rel_path"
        link_file "$skill_file" "$HOME/.gemini/config/skills/$rel_path"
    done
fi

echo "==> Setup completed successfully!"
