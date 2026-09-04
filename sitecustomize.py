"""Load Nika runtime environment from the project directory before app imports."""
import os
from dotenv import load_dotenv

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_NAME = os.getenv("NIKA_ENV_FILE", ".env")
_ENV_PATH = _ENV_NAME if os.path.isabs(_ENV_NAME) else os.path.join(_PROJECT_DIR, _ENV_NAME)
load_dotenv(_ENV_PATH, override=True)
