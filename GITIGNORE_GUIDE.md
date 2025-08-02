# Git Ignore Guide for RV Media Player

This document explains what files are ignored by git and why, to help maintain security and keep the repository clean.

## 🔒 Security-Sensitive Files (NEVER COMMIT)

### Configuration Files
- `config/app_config.json` - Contains encrypted Jellyfin credentials and API keys
- `.env` files - Environment variables with secrets
- `*.key`, `*.pem` - SSL certificates and private keys
- `secrets.json`, `api_keys.json` - Any files containing API keys or secrets

### Why: These files contain sensitive information that could compromise security if exposed.

## 📊 Runtime Data (NEVER COMMIT)

### Logs and Databases
- `logs/*.log` - Application log files (can be very large)
- `*.db`, `*.sqlite*` - Database files with user data
- `media/local_media.db` - Local media database
- `cache/` - Application cache directories

### Media Files
- `media/movies/` - Local movie files
- `media/tv-shows/` - Local TV show files  
- `media/downloads/` - Downloaded content
- `thumbnails/` - Generated thumbnail images

### Why: These files are generated at runtime, can be very large, and contain user-specific data.

## 🐍 Python Development Files (NEVER COMMIT)

### Compiled Python
- `__pycache__/` - Python bytecode cache
- `*.pyc`, `*.pyo` - Compiled Python files
- `*.so` - C extension modules

### Virtual Environments
- `venv/`, `env/` - Python virtual environments
- `.venv/` - Alternative virtual environment names

### Testing and Coverage
- `.pytest_cache/` - Pytest cache
- `htmlcov/` - Coverage reports
- `.coverage` - Coverage data files

### Why: These are generated files that should be recreated in each environment.

## 💻 Development Environment Files (NEVER COMMIT)

### IDEs and Editors
- `.vscode/` - VS Code settings
- `.idea/` - PyCharm/IntelliJ settings
- `*.swp`, `*.swo` - Vim swap files

### Operating System
- `.DS_Store` - macOS metadata
- `Thumbs.db` - Windows thumbnails
- `Desktop.ini` - Windows folder settings

### Why: These are environment-specific and would conflict between developers.

## 🔧 Temporary and Backup Files (NEVER COMMIT)

### Temporary Files
- `tmp/`, `temp/` - Temporary directories
- `*.tmp`, `*.temp` - Temporary files
- `*.bak`, `*.backup` - Backup files

### Development Files
- `run.bat` - Windows-specific development scripts
- `setup.bat` - Windows batch files
- `vlc-help.txt` - Development notes

### Why: These are temporary or development-specific files not needed for deployment.

## ✅ What SHOULD Be Committed

### Application Code
- `app/` - All Python application code
- `static/` - CSS, JavaScript, images
- `templates/` - HTML templates

### Configuration Templates
- `config/*.template` - Configuration file templates
- `systemd/*.service` - Service configuration files
- `requirements.txt` - Python dependencies

### Documentation
- `README*.md` - Documentation files
- `LICENSE` - License file
- Installation and setup scripts

### Infrastructure
- `install.sh` - Installation script
- `setup_config.sh` - Configuration script
- `.gitignore` - This file!

## 🏗️ Directory Structure

```
rv-media-player/
├── .gitignore              ✅ Commit
├── README.md               ✅ Commit
├── requirements.txt        ✅ Commit
├── install.sh             ✅ Commit
├── app/                   ✅ Commit (code only)
│   └── __pycache__/       ❌ Ignore
├── config/
│   ├── *.template         ✅ Commit
│   └── app_config.json    ❌ Ignore (sensitive)
├── logs/
│   ├── .gitkeep          ✅ Commit
│   └── *.log             ❌ Ignore
├── media/
│   ├── .gitkeep          ✅ Commit
│   ├── *.db              ❌ Ignore
│   └── movies/           ❌ Ignore (content)
├── static/               ✅ Commit
├── templates/            ✅ Commit
├── systemd/              ✅ Commit
└── venv/                 ❌ Ignore
```

## 🚨 Security Checklist

Before committing, always check:

1. **No credentials**: Search for passwords, API keys, tokens
2. **No personal data**: No user databases or personal files
3. **No large files**: No media files or large logs
4. **No environment files**: No `.env` or local config files

### Quick Security Check Commands

```bash
# Check for potential secrets
grep -r -i "password\|api_key\|secret\|token" . --exclude-dir=.git

# Check file sizes (flag anything > 1MB)
find . -size +1M -type f | grep -v .git

# Check for sensitive file patterns
find . -name "*.key" -o -name "*.pem" -o -name ".env*"
```

## 🔄 Cleaning Up Accidentally Committed Files

If you accidentally commit sensitive files:

```bash
# Remove from git but keep locally
git rm --cached config/app_config.json

# Remove from git and delete locally
git rm config/app_config.json

# Remove from entire git history (DANGEROUS)
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch config/app_config.json' \
  --prune-empty --tag-name-filter cat -- --all
```

## 📝 Best Practices

1. **Review before commit**: Always check `git status` and `git diff` before committing
2. **Use templates**: Copy `.template` files and customize locally
3. **Environment variables**: Use `.env` files for local configuration
4. **Regular cleanup**: Periodically clean up ignored files with `git clean -fdx`
5. **Team coordination**: Ensure all team members understand what should/shouldn't be committed

Remember: It's much easier to prevent sensitive data from being committed than to remove it after the fact!
