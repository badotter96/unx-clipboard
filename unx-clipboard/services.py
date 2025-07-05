import os
import io
import shutil
import zipfile
import time
import json
import csv
import sqlite3
from datetime import datetime, timezone
from abc import ABC, abstractmethod

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from config import (
    USER_DATA_DIR, IMAGES_PATH, DB_PATH, CONFIG_FILE_PATH
)

# --- SYNC STATE HELPERS ---
SYNC_STATE_FILE = os.path.join(USER_DATA_DIR, 'sync_state.json')

def get_local_sync_state():
    """Gets the state of the last successful sync."""
    try:
        with open(SYNC_STATE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sync_id": None, "last_sync_time": None}

def save_local_sync_state(sync_id):
    """Saves the state of the current sync."""
    state = {
        "sync_id": sync_id,
        "last_sync_time": datetime.now(timezone.utc).isoformat()
    }
    with open(SYNC_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

# --- SERVICE CLASSES ---

class ImportExport:
    def __init__(self, db):
        self.db = db
        self.parent = None

    def _show_message(self, title, text, icon_type="information"):
        if self.parent:
            icon = QMessageBox.Critical if icon_type == "critical" else QMessageBox.Information
            QMessageBox(icon, title, text, QMessageBox.Ok, self.parent).exec_()

    def export_full_backup(self, file_path):
        """Creates a .unxbackup zip file containing all user data."""
        if not file_path.endswith('.unxbackup'):
            file_path += '.unxbackup'
        
        try:
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                if os.path.exists(DB_PATH):
                    zipf.write(DB_PATH, os.path.basename(DB_PATH))
                if os.path.exists(CONFIG_FILE_PATH):
                    zipf.write(CONFIG_FILE_PATH, os.path.basename(CONFIG_FILE_PATH))
                if os.path.isdir(IMAGES_PATH):
                    for root, _, files in os.walk(IMAGES_PATH):
                        for file in files:
                            full_file_path = os.path.join(root, file)
                            zipf.write(full_file_path, os.path.relpath(full_file_path, USER_DATA_DIR))
            self._show_message("Success", f"Full backup created at:\n{file_path}")
        except Exception as e:
            self._show_message("Error", f"Failed to create backup: {e}", "critical")

    def import_full_backup(self, file_path):
        """Restores user data from a .unxbackup file."""
        reply = QMessageBox.warning(self.parent, "Confirm Restore",
            "This will overwrite all current settings, history, and images. "
            "The application will restart. Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            return False

        try:
            self.db.close()
            
            if os.path.isdir(IMAGES_PATH): shutil.rmtree(IMAGES_PATH)
            if os.path.exists(CONFIG_FILE_PATH): os.remove(CONFIG_FILE_PATH)
            if os.path.exists(DB_PATH): os.remove(DB_PATH)

            with zipfile.ZipFile(file_path, 'r') as zipf:
                os.makedirs(USER_DATA_DIR, exist_ok=True)
                zipf.extractall(USER_DATA_DIR)
            
            self._show_message("Restore Complete", "The application will now restart to apply the restored data.")
            return True
        except Exception as e:
            self._show_message("Error", f"Failed to restore from backup: {e}", "critical")
            self.db.re_init()
            return False

class NotionIntegration:
    def __init__(self, config):
        self.config = config.get('notion', {})
        self.enabled = self.config.get('enabled', False)
        self.api_key = self.config.get('api_key')
        self.database_id = self.config.get('database_id')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }

    def is_configured(self):
        return self.enabled and self.api_key and self.database_id

    def send_entry(self, content, content_type, timestamp):
        if not self.is_configured():
            return False, "Notion not configured in settings."
        
        api_url = "https://api.notion.com/v1/pages"
        title_content = (content[:100] + '...') if len(content) > 100 else content
        
        page_data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Title": {"title": [{"text": {"content": title_content.strip()}}]},
                "Content": {"rich_text": [{"text": {"content": content}}]},
                "Type": {"rich_text": [{"text": {"content": content_type}}]},
                "Timestamp": {"rich_text": [{"text": {"content": str(timestamp)}}]}
            }
        }
        try:
            response = requests.post(api_url, headers=self.headers, data=json.dumps(page_data))
            response.raise_for_status()
            return True, "Entry sent to Notion."
        except Exception as e:
            return False, f"Error sending to Notion: {e}"

class BaseSyncProvider(ABC):
    SYNC_FILENAME = "clipboard_backup.unxbackup"

    def __init__(self, config, db, gui_parent=None):
        self.config = config
        self.db = db
        self.gui_parent = gui_parent
    
    @abstractmethod
    def sync(self):
        pass

class LocalFolderProvider(BaseSyncProvider):
    def sync(self):
        sync_path = self.config.get('local_sync_path')
        if not sync_path or not os.path.isdir(sync_path):
            print("Local sync path not configured or not found.")
            return

        destination_file = os.path.join(sync_path, self.SYNC_FILENAME)
        
        if not os.path.exists(DB_PATH) and os.path.exists(destination_file):
            print("Local database missing. Restoring from sync folder...")
            self.gui_parent.app_callbacks['importer_exporter'].import_full_backup(destination_file)
            return

        if os.path.exists(destination_file):
            remote_mtime = os.path.getmtime(destination_file)
            local_mtime = os.path.getmtime(DB_PATH)
            
            if remote_mtime > local_mtime:
                reply = QMessageBox.question(self.gui_parent, 'Sync Conflict',
                    "The backup in your sync folder is newer than your current data.\n\n"
                    "Would you like to restore from the sync folder? This will overwrite your current session and restart the app.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                
                if reply == QMessageBox.Yes:
                    if self.gui_parent.app_callbacks['importer_exporter'].import_full_backup(destination_file):
                        self.gui_parent.app_callbacks['restart_app']()
                return

        print("Local data is newer. Backing up to sync folder.")
        importer = ImportExport(self.db)
        importer.export_full_backup(destination_file)

class CloudSync:
    def __init__(self, config, db, gui_parent=None):
        self.config = config.get('sync', {})
        self.db = db
        self.gui_parent = gui_parent
        self.provider = self._get_provider()

    def _get_provider(self):
        backend = self.config.get('backend', 'None').lower()
        if backend == 'localfolder':
            return LocalFolderProvider(self.config, self.db, self.gui_parent)
        return None

    def sync(self):
        if self.provider:
            self.provider.sync()
