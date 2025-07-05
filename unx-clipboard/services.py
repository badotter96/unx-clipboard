import os
import io
import shutil
import requests
import zipfile
import time
import json
import csv
import sqlite3
from datetime import datetime, timezone, timedelta
from abc import ABC, abstractmethod

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from config import (
    GOOGLE_TOKEN_PATH, ONEDRIVE_TOKEN_PATH, 
    GOOGLE_CREDS_PATH, IMAGES_PATH, DB_PATH, CONFIG_FILE_PATH,
    USER_DATA_DIR
)

# --- SYNC STATE HELPERS ---
SYNC_STATE_FILE = os.path.join(USER_DATA_DIR, 'sync_state.json')

def get_local_sync_state():
    try:
        with open(SYNC_STATE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sync_id": None}

def save_local_sync_state(sync_id):
    state = {"sync_id": sync_id}
    with open(SYNC_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

# --- SERVICE CLASSES ---

class ImportExport:
    def __init__(self, db):
        self.db = db
        self.parent = None

    def _get_all_data(self):
        return self.db.conn.execute("SELECT content, type, timestamp, pinned, is_snippet FROM clipboard ORDER BY timestamp DESC").fetchall()

    def _show_message(self, title, text, icon_type="information"):
        if self.parent:
            icon = QMessageBox.Critical if icon_type == "critical" else QMessageBox.Information
            QMessageBox(icon, title, text, QMessageBox.Ok, self.parent).exec_()

    def export_full_backup(self, filepath):
        if not filepath.endswith('.unxbackup'):
            filepath += '.unxbackup'
        
        try:
            with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                if os.path.exists(DB_PATH):
                    zipf.write(DB_PATH, os.path.basename(DB_PATH))
                if os.path.exists(CONFIG_FILE_PATH):
                    zipf.write(CONFIG_FILE_PATH, os.path.basename(CONFIG_FILE_PATH))
                if os.path.isdir(IMAGES_PATH):
                    for root, _, files in os.walk(IMAGES_PATH):
                        for file in files:
                            file_path = os.path.join(root, file)
                            zipf.write(file_path, os.path.relpath(file_path, USER_DATA_DIR))
            self._show_message("Success", f"Full backup created at:\n{filepath}")
        except Exception as e:
            self._show_message("Error", f"Failed to create backup: {e}", "critical")

    def import_full_backup(self, filepath):
        reply = QMessageBox.warning(self.parent, "Confirm Restore",
            "This will overwrite all current settings, history, and images. "
            "The application will restart. Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            return False

        try:
            self.db.close()
            
            if os.path.isdir(IMAGES_PATH):
                shutil.rmtree(IMAGES_PATH)
            if os.path.exists(CONFIG_FILE_PATH):
                os.remove(CONFIG_FILE_PATH)
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            
            with zipfile.ZipFile(filepath, 'r') as zipf:
                os.makedirs(USER_DATA_DIR, exist_ok=True)
                zipf.extractall(USER_DATA_DIR)
            
            self._show_message("Restore Complete", "The application will now restart to apply the restored data.")
            return True
        except Exception as e:
            self._show_message("Error", f"Failed to restore from backup: {e}", "critical")
            self.db.re_init()
            return False

    def export_to_json(self, filepath):
        data = [{"content": d[0], "type": d[1], "timestamp": str(d[2]), "pinned": d[3], "is_snippet": d[4]} for d in self._get_all_data()]
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            self._show_message("Success", f"Exported to {filepath}")
        except Exception as e:
            self._show_message("Error", f"Failed to export: {e}", "critical")

    def export_to_csv(self, filepath):
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['content', 'type', 'timestamp', 'pinned', 'is_snippet'])
                writer.writerows(self._get_all_data())
            self._show_message("Success", f"Exported to {filepath}")
        except Exception as e:
            self._show_message("Error", f"Failed to export to CSV: {e}", "critical")

    def export_to_markdown(self, filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("| Pinned | Snippet | Type | Timestamp | Content |\n")
                f.write("|---|---|---|---|---|\n")
                for row in self._get_all_data():
                    content, ctype, ts, pinned, snippet = row
                    safe_content = str(content or '').replace('\n', ' ').replace('|', '\\|')
                    ctype_str = str(ctype or '')
                    ts_str = str(ts or '')
                    pinned_str = 'Yes' if pinned else 'No'
                    snippet_str = 'Yes' if snippet else 'No'
                    f.write(f"| {pinned_str} | {snippet_str} | {ctype_str} | {ts_str} | {safe_content} |\n")
            self._show_message("Success", f"Exported to {filepath}")
        except Exception as e:
            self._show_message("Error", f"Failed to export to Markdown: {e}", "critical")

    def export_to_sqlite(self, filepath):
        try:
            if not filepath.endswith('.db'):
                filepath += '.db'
            shutil.copyfile(self.db.db_path, filepath)
            self._show_message("Success", f"Backed up database to {filepath}")
        except Exception as e:
            self._show_message("Error", f"Failed to backup: {e}", "critical")
            
    def _insert_data(self, data_list):
        count = 0
        with self.db.conn:
            for item in data_list:
                timestamp_str = item.get('timestamp')
                timestamp_obj = None

                if isinstance(timestamp_str, datetime):
                    timestamp_obj = timestamp_str
                elif isinstance(timestamp_str, str):
                    try:
                        timestamp_obj = datetime.fromisoformat(timestamp_str)
                    except (TypeError, ValueError):
                        timestamp_obj = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    continue
                
                if not self.db.conn.execute("SELECT id FROM clipboard WHERE timestamp = ?", (timestamp_obj,)).fetchone():
                    self.db.conn.execute(
                        "INSERT INTO clipboard (content, type, timestamp, pinned, is_snippet) VALUES (?, ?, ?, ?, ?)",
                        (item.get('content'), item.get('type'), timestamp_obj, int(item.get('pinned', 0)), int(item.get('is_snippet', 0)))
                    )
                    count += 1
        return count

    def import_from_json(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            count = self._insert_data(data)
            self._show_message("Success", f"Imported {count} new entries.")
            return True
        except Exception as e:
            self._show_message("Error", f"Failed to import from JSON: {e}", "critical")
            return False

    def import_from_csv(self, filepath):
        try:
            data = []
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
            count = self._insert_data(data)
            self._show_message("Success", f"Imported {count} new entries.")
            return True
        except Exception as e:
            self._show_message("Error", f"Failed to import from CSV: {e}", "critical")
            return False

    def import_from_sqlite(self, filepath):
        try:
            source_conn = sqlite3.connect(filepath, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
            source_entries = source_conn.cursor().execute("SELECT content, type, timestamp, pinned, is_snippet FROM clipboard").fetchall()
            source_conn.close()
            data = [{"content":d[0],"type":d[1],"timestamp":d[2],"pinned":d[3],"is_snippet":d[4]} for d in source_entries]
            count = self._insert_data(data)
            self._show_message("Success", f"Imported {count} new entries.")
            return True
        except Exception as e:
            self._show_message("Error", f"Failed to import from SQLite: {e}", "critical")
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
            return False, "Notion not configured."
        
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
            import requests
            response = requests.post(api_url, headers=self.headers, data=json.dumps(page_data))
            response.raise_for_status()
            return True, "Entry sent to Notion."
        except Exception as e:
            return False, f"Error sending to Notion: {e}"

class BaseSyncProvider(ABC):
    SYNC_FILENAME = "clipboard_sync.zip"
    def __init__(self, config, db, gui_parent=None):
        self.config = config; self.db = db; self.gui_parent = gui_parent
        self.temp_zip_path = os.path.join(USER_DATA_DIR, "temp_sync_archive.zip")
    
    def sync(self, force_upload=False):
        """Public method to initiate a sync."""
        if not self._authenticate(): return
        self._perform_sync(force_upload)
    
    def log_in(self): return self._authenticate()
    
    @abstractmethod
    def is_logged_in(self) -> bool: pass
    @abstractmethod
    def log_out(self): pass
    @abstractmethod
    def _authenticate(self) -> bool: pass
    @abstractmethod
    def _upload_archive(self, file_id_to_update=None): pass
    @abstractmethod
    def _download_archive(self, remote_file_meta): pass
    @abstractmethod
    def _get_remote_metadata(self): pass

    def _perform_sync(self, force_upload=False):
        """The main sync logic controller."""
        print("Checking cloud sync status...")
        remote_meta = self._get_remote_metadata()
        local_state = get_local_sync_state()
        local_sync_id = local_state.get('sync_id')

        # Scenario 1: User explicitly forces an upload (from manual sync button)
        if force_upload:
            print("Forcing upload of local changes...")
            self._upload_archive(remote_meta.get('id') if remote_meta else None)
            return

        # Scenario 2: No backup exists on the cloud. Perform initial upload.
        if not remote_meta:
            print("No remote backup found. Performing initial upload...")
            self._upload_archive()
            return
            
        remote_sync_id = remote_meta.get('properties', {}).get('sync_id')

        # Scenario 3: This is a new client (no local sync history). Always download.
        if not local_sync_id:
            print("New client detected. Downloading from cloud to initialize...")
            self._download_archive(remote_meta)
            return

        # Scenario 4: Cloud has been updated by another client. Download changes.
        if remote_sync_id and remote_sync_id != local_sync_id:
            print("Remote changes detected. Downloading from cloud...")
            self._download_archive(remote_meta)
            return

        # Scenario 5: No changes anywhere.
        print("Data is already in sync.")

    def _cleanup_temp_files(self, *files):
        def do_cleanup():
            for f in files:
                try:
                    if os.path.exists(f): os.remove(f)
                except OSError: QTimer.singleShot(2000, lambda: self._cleanup_temp_files(f))
        QTimer.singleShot(2000, do_cleanup)

    def _create_zip_archive(self):
        with zipfile.ZipFile(self.temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if os.path.exists(DB_PATH):
                zipf.write(DB_PATH, os.path.basename(DB_PATH))
            if os.path.exists(CONFIG_FILE_PATH):
                zipf.write(CONFIG_FILE_PATH, os.path.basename(CONFIG_FILE_PATH))
            if os.path.isdir(IMAGES_PATH):
                for root, _, files in os.walk(IMAGES_PATH):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, USER_DATA_DIR))
        return self.temp_zip_path

    def _extract_zip_archive(self, zip_filepath):
        # This is non-destructive. It will overwrite existing files but not delete local-only ones.
        with zipfile.ZipFile(zip_filepath, 'r') as zipf:
            zipf.extractall(USER_DATA_DIR)

class LocalFolderProvider(BaseSyncProvider):
    def _authenticate(self) -> bool:
        return True
    def is_logged_in(self) -> bool:
        return False
    def log_out(self):
        pass
    def _perform_sync(self):
        # This provider doesn't support intelligent sync, it's just a one-way copy
        sync_path = self.config.get('local_sync_path')
        if not sync_path or not os.path.isdir(sync_path):
            return
        destination_file = os.path.join(sync_path, self.SYNC_FILENAME)
        archive_path = self._create_zip_archive()
        try:
            shutil.copy(archive_path, destination_file)
        finally:
            self._cleanup_temp_files(archive_path)

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

    def sync(self, force_upload=False): # force_upload is unused but kept for compatibility
        if self.provider:
            self.provider.sync()

    def is_logged_in(self):
        return False # Direct login is no longer a feature

    def log_in(self):
        return False

    def log_out(self):
        pass