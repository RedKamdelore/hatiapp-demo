#!/bin/bash
cd /home/RedKamdelore
python3.10 -m venv myenv
source myenv/bin/activate
pip install fastapi uvicorn sqlalchemy pydantic-settings python-jose passlib python-multipart jinja2 slowapi qrcode pillow
echo "Setup complete!"