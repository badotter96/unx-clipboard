import os
import io
import shutil
import requests
import zipfile
import time
import json
import csv
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from abc import ABC, abstractmethod

from PyQt5.QtCore import QTimer, QObject, pyqtSignal
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
            self.db.conn.execute("PRAGMA wal_checkpoint(FULL);")
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

class SyncSignals(QObject):
    """A communicator to safely pass sync results from background threads to the main thread."""
    sync_complete = pyqtSignal(bool, str) # bool: success, str: message

class BaseSyncProvider(ABC):
    SYNC_FILENAME = "clipboard_sync.zip"
    def __init__(self, config, db, signals):
        self.full_config = config
        self.config = self.full_config.get('sync', {})
        self.db = db
        self.signals = signals
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
        self.db.conn.execute("PRAGMA wal_checkpoint(FULL);")
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
    def _get_remote_metadata(self):
        pass

    def _upload_archive(self, file_id_to_update=None):
        pass
    def _download_archive(self, remote_file_meta):
        pass
    def _authenticate(self) -> bool:
        return True
    def is_logged_in(self) -> bool:
        return False
    def log_out(self):
        pass
    def sync(self, force_upload=False):
        """
        Directly overrides the base sync method. It now finds the active
        profile from the list of profiles in the configuration.
        """
        backend_name = self.config.get('backend', 'None')
        
        # Check if a sync was manually triggered without a profile selected
        if backend_name == "None":
            message = "No active sync profile selected.\nPlease select a profile on application startup to enable sync."
            print(message)
            if force_upload: # Only show this error popup on a manual sync attempt
                 self.signals.sync_complete.emit(False, message)
            return

        # Find the active profile from the list by its name
        profiles = self.full_config.get('sync', {}).get('profiles', [])
        active_profile = next((p for p in profiles if p.get('name') == backend_name), None)
        
        if not active_profile:
            message = f"Error: Active sync profile '{backend_name}' could not be found in your configuration."
            print(message)
            self.signals.sync_complete.emit(False, message)
            return

        sync_path = active_profile.get('path')
        retention_count = active_profile.get('retention', 5)
        print(f"Performing sync for profile '{backend_name}' to path: {sync_path}")

        if not sync_path or not os.path.isdir(sync_path):
            message = f"The path for profile '{backend_name}' is not configured or is not a valid directory."
            print(message)
            self.signals.sync_complete.emit(False, message)
            return
            
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{os.path.splitext(self.SYNC_FILENAME)[0]}_{timestamp_str}.zip"
        destination_file = os.path.join(sync_path, unique_filename)
        
        try:
            archive_path = self._create_zip_archive()
            shutil.copy(archive_path, destination_file)
            message = f"Backup successfully created for profile '{backend_name}'."
            print(f"Successfully synced backup to {destination_file}")
            
            self._save_last_sync_info()
            self._apply_retention_policy(sync_path, retention_count)

            # Only emit a success signal, the popup is no longer needed
            self.signals.sync_complete.emit(True, message)
        except Exception as e:
            message = f"Could not complete sync for profile '{backend_name}':\n{e}"
            print(f"Error during local folder sync: {e}")
            self.signals.sync_complete.emit(False, message)
        finally:
            if 'archive_path' in locals() and os.path.exists(archive_path):
                self._cleanup_temp_files(archive_path)

    def _apply_retention_policy(self, sync_path):
        """Deletes older backup files, keeping only the specified number."""
        retention_count = self.config.get('backup_retention_count', 5)
        if retention_count == 0:
            return # Retention is disabled

        try:
            # Get all .zip files that match our sync filename pattern
            backups = [f for f in os.listdir(sync_path) if f.startswith(os.path.splitext(self.SYNC_FILENAME)[0]) and f.endswith(".zip")]
            
            if len(backups) <= retention_count:
                return # Not enough backups to apply policy

            # Sort files by modification time (oldest first)
            backups.sort(key=lambda f: os.path.getmtime(os.path.join(sync_path, f)))
            
            # Calculate how many files to delete
            files_to_delete_count = len(backups) - retention_count
            files_to_delete = backups[:files_to_delete_count]

            print(f"Applying retention policy: Deleting {len(files_to_delete)} old backup(s)...")
            for f in files_to_delete:
                os.remove(os.path.join(sync_path, f))
        except Exception as e:
            print(f"Error applying retention policy: {e}")

    def _save_last_sync_info(self):
        """Saves the current timestamp to a state file."""
        state = {"last_sync_timestamp": datetime.now().isoformat()}
        state_file = os.path.join(USER_DATA_DIR, 'last_sync_info.json')
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=4)

class CloudSync:
    def __init__(self, config, db, signals):
        self.full_config = config
        self.config = self.full_config.get('sync', {})
        self.db = db
        self.signals = signals
        self.provider = self._get_provider()

    def _get_provider(self):
        backend = self.config.get('backend', 'None').lower()
        if backend == 'localfolder':
            return LocalFolderProvider(self.full_config, self.db, self.signals)
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

class DiscordIntegration:
    def __init__(self, config):
        self.config = config.get('discord', {})
        self.enabled = self.config.get('enabled', False)
        self.webhook_url = self.config.get('webhook_url')
        self.text_thread_id = self.config.get('text_thread_id')
        self.image_thread_id = self.config.get('image_thread_id')
        self.snippet_thread_id = self.config.get('snippet_thread_id')

    def send_snippet_to_discord(self, key, value):
        """Sends a key-value snippet to the dedicated snippet thread."""
        if not self.enabled or not self.webhook_url or not self.snippet_thread_id:
            return

        final_url = f"{self.webhook_url}?thread_id={self.snippet_thread_id}"
        
        try:
            # --- THE CORRECTED LOGIC ---
            # We check if the BASENAME of the path starts with our unique prefix.
            # This correctly identifies "images/unxss-region-123.png" as an image.
            if value and isinstance(value, str) and os.path.basename(value).startswith('unxss-'):
                # It's an image. Send the key as text and the image as a file.
                image_path = os.path.join(USER_DATA_DIR, value)
                if not os.path.exists(image_path):
                    print(f"DiscordIntegration: Snippet image not found at {image_path}")
                    return
                
                with open(image_path, 'rb') as f:
                    payload = {'content': f"**{key}**"} # The key is the text part of the message
                    files = {'file': (os.path.basename(image_path), f)}
                    response = requests.post(final_url, data=payload, files=files)

            else:
                # It's text. Send the formatted key-value pair.
                formatted_content = f"**{key}**:\n```\n{value}\n```"
                payload = {'content': formatted_content}
                response = requests.post(final_url, json=payload)
            # --- END OF CORRECTED LOGIC ---

            response.raise_for_status()
            print(f"Successfully sent snippet '{key}' to Discord.")
        except requests.exceptions.RequestException as e:
            print(f"Error sending snippet to Discord: {e}")

    def send_to_discord(self, content, content_type):
        # Determine which thread ID to use
        if content_type == 'text':
            thread_id = self.text_thread_id
        elif content_type == 'image':
            thread_id = self.image_thread_id
        else:
            return # Do nothing if content_type is unknown

        # Only proceed if the feature is enabled and fully configured for this content type
        if not self.enabled or not self.webhook_url or not thread_id:
            return

        # Construct the final URL with the correct thread_id parameter
        final_url = f"{self.webhook_url}?thread_id={thread_id}"
        
        try:
            if content_type == 'text':
                payload = {'content': content}
                response = requests.post(final_url, json=payload)
            elif content_type == 'image':
                image_path = os.path.join(USER_DATA_DIR, content)
                if not os.path.exists(image_path):
                    print(f"DiscordIntegration: Image not found at {image_path}")
                    return
                
                with open(image_path, 'rb') as f:
                    files = {'file': (os.path.basename(image_path), f)}
                    response = requests.post(final_url, files=files)
            
            response.raise_for_status()
            print(f"Successfully sent {content_type} to Discord thread {thread_id}.")
        except requests.exceptions.RequestException as e:
            print(f"Error sending to Discord: {e}")