#!/bin/bash
# HatiApp VPS Deploy Script
# Run on Ubuntu 22.04 server

set -e

APP_DIR="/opt/hatiapp"
SERVICE_NAME="hatiapp"

echo "=========================================="
echo "  HatiApp VPS Installer"
echo "=========================================="

# Update system
echo "[1/6] Updating system..."
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx sqlite3

# Create app directory
echo "[2/6] Creating app directory..."
mkdir -p $APP_DIR
cd $APP_DIR

# Create virtual environment
echo "[3/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# Install dependencies
echo "[4/6] Installing dependencies..."
pip install fastapi uvicorn sqlalchemy pydantic-settings python-jose passlib python-multipart jinja2 slowapi qrcode pillow

# Create systemd service
echo "[5/6] Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << 'EOF'
[Unit]
Description=HatiApp Volunteer Schedule
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/hatiapp
Environment=PATH=/opt/hatiapp/venv/bin
ExecStart=/opt/hatiapp/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create nginx config (optional - for domain)
cat > /etc/nginx/sites-available/hatiapp << 'EOF'
server {
    listen 80;
    server_name _;  # Accept any hostname/IP
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /static {
        alias /opt/hatiapp/static;
        expires 1d;
    }
}
EOF

ln -sf /etc/nginx/sites-available/hatiapp /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Enable services
echo "[6/6] Enabling services..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl enable nginx

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Upload your project files to /opt/hatiapp"
echo "2. Run: cd /opt/hatiapp && sqlite3 app.db < your_backup.sql (optional)"
echo "3. Start service: systemctl start hatiapp"
echo "4. Open firewall: ufw allow 80/tcp && ufw allow 8000/tcp"
echo ""
echo "Your app will be available at:"
echo "  http://YOUR_SERVER_IP:8000"
echo "  or http://YOUR_SERVER_IP (via nginx)"
echo ""
