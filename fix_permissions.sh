#!/bin/bash
# Quick fix script for RV Media Player permission issues
# Run this as root to fix the current installation

echo "Fixing RV Media Player permissions and directory issues..."

# Configuration
APP_DIR="/opt/rv-media-player"

# Stop the service
systemctl stop rv-media-player.service 2>/dev/null || true

# Fix ownership
echo "Setting proper ownership..."
chown -R media:media "$APP_DIR"

# Fix permissions
echo "Setting proper permissions..."
chmod 755 "$APP_DIR"
chmod 755 "$APP_DIR/logs" 2>/dev/null || mkdir -p "$APP_DIR/logs" && chown media:media "$APP_DIR/logs" && chmod 755 "$APP_DIR/logs"
chmod 700 "$APP_DIR/config"
chmod 600 "$APP_DIR/config/app_config.json" 2>/dev/null || true

# Ensure logs directory exists with correct permissions
echo "Ensuring logs directory exists..."
sudo -u media mkdir -p "$APP_DIR/logs"
sudo -u media chmod 755 "$APP_DIR/logs"

# Test the application startup
echo "Testing application startup..."
cd "$APP_DIR"
sudo -u media -H bash -c "
    source venv/bin/activate
    python -c \"from app.app import create_app; app = create_app(); print('✓ Application started successfully')\"
"

# Update systemd service with fixes
echo "Updating systemd service..."
cat > /etc/systemd/system/rv-media-player.service << EOF
[Unit]
Description=RV Media Player - Jellyfin Offline Media Server
Documentation=https://github.com/your-repo/rv-media-player
After=network-online.target
Wants=network-online.target
Requires=rv-media-player-optimize.service

[Service]
Type=simple
User=media
Group=media
SupplementaryGroups=audio video dialout plugdev
WorkingDirectory=$APP_DIR
Environment=PYTHONPATH=$APP_DIR
Environment=FLASK_APP=app.py
Environment=FLASK_ENV=production
ExecStartPre=/bin/mkdir -p $APP_DIR/logs
ExecStartPre=/bin/chown media:media $APP_DIR/logs
ExecStart=$APP_DIR/venv/bin/python -m app.app
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rv-media-player

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR /media /tmp

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

# Process priority
Nice=-5

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and restart service
echo "Reloading systemd and starting service..."
systemctl daemon-reload
systemctl start rv-media-player.service

# Check service status
echo "Checking service status..."
systemctl status rv-media-player.service --no-pager

echo ""
echo "Fix completed! The service should now be running."
echo "Check logs with: sudo journalctl -u rv-media-player -f"
echo "Access the web interface at: http://$(hostname -I | awk '{print $1}'):5000"
