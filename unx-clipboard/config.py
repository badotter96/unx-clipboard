import os
import sys

def resource_path(relative_path):
    """ Get absolute path to a resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Not running in a PyInstaller bundle, so base is the project root
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_user_data_dir():
    """Gets the path to the user's data folder for our app."""
    if sys.platform == 'win32':
        # Path is C:\Users\<Username>\AppData\Roaming\UNX Clipboard
        path = os.path.join(os.environ['APPDATA'], 'UNX Clipboard')
    else: # for macOS and Linux
        path = os.path.join(os.path.expanduser('~'), '.unxclipboard')
    os.makedirs(path, exist_ok=True)
    return path

# This is the single source of truth for user's writable data
USER_DATA_DIR = get_user_data_dir()

# --- Paths for writable data ---
CONFIG_FILE_PATH = os.path.join(USER_DATA_DIR, 'config.json')
DB_PATH = os.path.join(USER_DATA_DIR, 'clipboard_history.db')
IMAGES_PATH = os.path.join(USER_DATA_DIR, 'images')
THEMES_PATH = os.path.join(USER_DATA_DIR, 'themes')
GOOGLE_CREDS_PATH = os.path.join(USER_DATA_DIR, 'credentials.json')
GOOGLE_TOKEN_PATH = os.path.join(USER_DATA_DIR, 'google_token.json')
ONEDRIVE_TOKEN_PATH = os.path.join(USER_DATA_DIR, 'onedrive_token_cache.json')
USER_ICON_PATH = os.path.join(USER_DATA_DIR, 'icon.ico')