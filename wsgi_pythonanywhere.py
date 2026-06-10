import sys
import os

# Path to your project
path = '/home/RedKamdelore/hatiapp'
if path not in sys.path:
    sys.path.insert(0, path)

os.chdir(path)

# Add virtualenv site-packages
import site
venv_site_packages = '/home/RedKamdelore/.virtualenvs/hatiapp/lib/python3.10/site-packages'
if venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)

from main import app
application = app
