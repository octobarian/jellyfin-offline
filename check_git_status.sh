#!/bin/bash

# Git Status Checker for RV Media Player
# This script helps verify what files would be committed and checks for sensitive data

echo "🔍 RV Media Player Git Status Check"
echo "=================================="
echo

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Not a git repository. Run 'git init' first."
    exit 1
fi

echo "📁 Files that would be committed:"
echo "--------------------------------"
git status --porcelain | grep -E "^(\?\?|A |M )" | head -20
echo

echo "🔒 Checking for sensitive files that should be ignored:"
echo "------------------------------------------------------"

# Check for configuration files with potential secrets
sensitive_files=()

if [ -f "config/app_config.json" ]; then
    echo "⚠️  Found: config/app_config.json (should be ignored)"
    sensitive_files+=("config/app_config.json")
fi

if [ -f ".env" ]; then
    echo "⚠️  Found: .env (should be ignored)"
    sensitive_files+=(".env")
fi

# Check for log files
if find logs/ -name "*.log" -type f 2>/dev/null | grep -q .; then
    echo "⚠️  Found: log files in logs/ (should be ignored)"
    sensitive_files+=("logs/*.log")
fi

# Check for database files
if find . -name "*.db" -o -name "*.sqlite*" 2>/dev/null | grep -q .; then
    echo "⚠️  Found: database files (should be ignored)"
    sensitive_files+=("*.db files")
fi

# Check for Python cache
if find . -name "__pycache__" -type d 2>/dev/null | grep -q .; then
    echo "⚠️  Found: __pycache__ directories (should be ignored)"
    sensitive_files+=("__pycache__")
fi

# Check for virtual environment
if [ -d "venv" ] || [ -d "env" ] || [ -d ".venv" ]; then
    echo "⚠️  Found: virtual environment directory (should be ignored)"
    sensitive_files+=("venv/env directories")
fi

if [ ${#sensitive_files[@]} -eq 0 ]; then
    echo "✅ No sensitive files found that would be committed"
else
    echo
    echo "❌ Found ${#sensitive_files[@]} types of files that should be ignored!"
    echo "   Make sure .gitignore is working correctly."
fi

echo
echo "🔍 Checking for potential secrets in tracked files:"
echo "--------------------------------------------------"

# Search for common secret patterns in files that would be committed
secret_patterns=(
    "password"
    "api_key"
    "secret"
    "token"
    "jellyfin.*key"
    "jellyfin.*password"
)

found_secrets=false
for pattern in "${secret_patterns[@]}"; do
    if git ls-files | xargs grep -l -i "$pattern" 2>/dev/null | grep -v ".gitignore\|GITIGNORE_GUIDE.md\|README"; then
        echo "⚠️  Found potential secrets matching: $pattern"
        found_secrets=true
    fi
done

if [ "$found_secrets" = false ]; then
    echo "✅ No obvious secrets found in tracked files"
fi

echo
echo "📊 Repository size check:"
echo "------------------------"
echo "Total files that would be tracked:"
git ls-files 2>/dev/null | wc -l || echo "0 (not initialized)"

echo
echo "Large files (>1MB) that would be tracked:"
git ls-files 2>/dev/null | xargs ls -la 2>/dev/null | awk '$5 > 1048576 {print $9, "(" $5 " bytes)"}' || echo "None found"

echo
echo "📋 Summary:"
echo "----------"
if [ ${#sensitive_files[@]} -eq 0 ] && [ "$found_secrets" = false ]; then
    echo "✅ Repository looks clean and secure!"
    echo "✅ Safe to commit and push"
else
    echo "❌ Issues found - review before committing!"
    echo "   See GITIGNORE_GUIDE.md for help"
fi

echo
echo "💡 Next steps:"
echo "  1. Review the files listed above"
echo "  2. Check .gitignore is working: git status"
echo "  3. If clean: git add . && git commit -m 'Initial commit'"
echo "  4. See GITIGNORE_GUIDE.md for security best practices"
