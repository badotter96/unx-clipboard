# create_build_files.py
import sqlite3
import os
import json

print("Preparing files for PyInstaller build...")

# --- Create the default config file in the root directory ---
CONFIG_FILE = 'config.json'
if os.path.exists(CONFIG_FILE):
    print(f"'{CONFIG_FILE}' already exists. Skipping creation.")
else:
    default_config = {
        "history": {"retention_days": 30, "max_entries_display": 500, "log_images": True},
        "sync": {"auto_sync": False, "backend": "None", "sync_interval_minutes": 15, "onedrive_client_id": "", "google_credentials_path": "credentials.json", "local_sync_path": ""},
        "hotkey": "<ctrl>+<shift>+v", "snipping_hotkey": "<ctrl>+<shift>+s", "theme": "System",
        "custom_theme": {"background": "#2e3440", "foreground": "#d8dee9", "background_light": "#3b4252", "accent_primary": "#81a1c1", "accent_secondary": "#5e81ac", "font_family": "Segoe UI", "font_size": "10pt"},
        "notion": {"enabled": False, "api_key": "", "database_id": ""}
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(default_config, f, indent=4)
    print(f"'{CONFIG_FILE}' created successfully.")


# --- Create the initial, structured database in the root directory ---
DB_NAME = 'clipboard_history.db'
if os.path.exists(DB_NAME):
    print(f"'{DB_NAME}' already exists. Skipping creation.")
else:
    conn = sqlite3.connect(DB_NAME)
    # Ensure the table and index exist in the bundled database
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clipboard (
            id INTEGER PRIMARY KEY,
            content TEXT NOT NULL,
            type TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            pinned INTEGER DEFAULT 0,
            is_snippet INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON clipboard (content);")
    conn.close()
    print(f"'{DB_NAME}' created successfully.")

print("\nBuild files are ready.")