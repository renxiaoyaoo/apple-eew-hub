#!/usr/bin/env sh
set -eu

repo_root="$(git rev-parse --show-toplevel)"
hook="$repo_root/.git/hooks/pre-commit"

cat > "$hook" <<'EOF'
#!/usr/bin/env sh
set -eu
python3 scripts/privacy_check.py
EOF

chmod +x "$hook"
echo "Installed pre-commit privacy check: $hook"
