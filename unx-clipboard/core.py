import sqlite3
import os
import time
from datetime import datetime, timedelta
from PyQt5.QtCore import QObject, pyqtSignal, QBuffer, QIODevice, QTimer
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication
import pyperclip
from PIL import Image, ImageGrab
from threading import Thread

def adapt_datetime(ts): return ts.strftime('%Y-%m-%d %H:%M:%S.%f')
def convert_timestamp(ts): return datetime.strptime(ts.decode('utf-8'), '%Y-%m-%d %H:%M:%S.%f')
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_timestamp)

class Communication(QObject):
    new_entry_detected = pyqtSignal()
    hotkey_triggered = pyqtSignal()
    open_settings_requested = pyqtSignal()
    snipping_tool_triggered = pyqtSignal()
    screenshot_taken_for_preview = pyqtSignal(str)
    history_cleared = pyqtSignal()

class Database:
    def __init__(self, db_path, config):
        self.db_path = db_path
        self.config = config
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
        # --- PERFORMANCE TUNING ---
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA cache_size = -4000;") # 4MB cache
        self.conn.execute("PRAGMA temp_store = MEMORY;")
        self.create_table()

    def re_init(self):
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)

    def create_table(self):
        with self.conn:
            try:
                self.conn.execute("ALTER TABLE clipboard ADD COLUMN is_snippet INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass # Column already exists
            
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS clipboard (
                    id INTEGER PRIMARY KEY,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    pinned INTEGER DEFAULT 0,
                    is_snippet INTEGER DEFAULT 0
                )
            """)
            # Add an index on the content column for faster searching
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON clipboard (content);")

    def add_entry(self, content, content_type):
        """Adds a new entry to the database, but only if it's not a recent duplicate."""
        with self.conn:
            cutoff_time = datetime.now() - timedelta(seconds=2)
            cursor = self.conn.execute(
                "SELECT id FROM clipboard WHERE content = ? AND type = ? AND timestamp > ?",
                (content, content_type, cutoff_time)
            )
            if cursor.fetchone():
                return

            self.conn.execute(
                "INSERT INTO clipboard (content, type, timestamp) VALUES (?, ?, ?)",
                (content, content_type, datetime.now())
            )

    def add_manual_snippet(self, content):
        with self.conn:
            self.conn.execute("INSERT INTO clipboard (content, type, timestamp, is_snippet) VALUES (?, 'text', ?, 1)", (content, datetime.now()))

    def get_total_entry_count(self, search_text=""):
        """Gets the total number of entries, optionally filtered by search text."""
        query = "SELECT COUNT(*) FROM clipboard"
        params = []
        if search_text:
            query += " WHERE content LIKE ?"
            params.append(f"%{search_text}%")
        
        cursor = self.conn.execute(query, params)
        count = cursor.fetchone()[0]
        return count

    def get_all_entries(self, search_text="", page=1, per_page=100):
        """Gets a paginated list of entries from the database."""
        query = "SELECT id, content, type, timestamp, pinned, is_snippet FROM clipboard"
        params = []
        if search_text:
            query += " WHERE content LIKE ?"
            params.append(f"%{search_text}%")
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        
        limit = per_page
        offset = (page - 1) * per_page
        params.extend([limit, offset])
        
        cursor = self.conn.execute(query, tuple(params))
        return cursor.fetchall()

    def toggle_pin(self, entry_id):
        with self.conn:
            cursor = self.conn.execute("SELECT pinned FROM clipboard WHERE id = ?", (entry_id,))
            current_status = cursor.fetchone()[0]
            self.conn.execute("UPDATE clipboard SET pinned = ? WHERE id = ?", (1 - current_status, entry_id))

    def set_as_snippet(self, entry_id):
        with self.conn:
            self.conn.execute("UPDATE clipboard SET is_snippet = 1 WHERE id = ?", (entry_id,))

    def remove_from_snippet(self, entry_id):
        with self.conn:
            self.conn.execute("UPDATE clipboard SET is_snippet = 0 WHERE id = ?", (entry_id,))

    def delete_entry(self, entry_id):
        with self.conn:
            self.conn.execute("DELETE FROM clipboard WHERE id = ?", (entry_id,))

    def apply_retention_policy(self):
        retention_days = self.config['history']['retention_days']
        if retention_days > 0:
            cutoff = datetime.now() - timedelta(days=retention_days)
            with self.conn:
                self.conn.execute("DELETE FROM clipboard WHERE pinned = 0 AND is_snippet = 0 AND timestamp < ?", (cutoff,))

    def clear_history(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT content FROM clipboard WHERE type='image' AND pinned=0 AND is_snippet=0")
        image_paths_to_delete = [row[0] for row in cursor.fetchall()]
        
        with self.conn:
            cursor.execute("DELETE FROM clipboard WHERE pinned = 0 AND is_snippet = 0")
        
        from config import USER_DATA_DIR
        for relative_path in image_paths_to_delete:
            try:
                full_path = os.path.join(USER_DATA_DIR, relative_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                print(f"Could not delete image file {relative_path}: {e}")

    def close(self):
        self.conn.close()

class ClipboardMonitor(QObject):
    """
    A QObject-based monitor that safely checks the clipboard on the main GUI thread
    using a QTimer.
    """
    new_entry = pyqtSignal(str, str)

    def __init__(self, config, images_path, parent=None):
        super().__init__(parent)
        self._config = config
        self.image_dir = images_path
        self._last_text = ""
        self._last_image_hash = None
        self._ignore_next_check = False

        # Initialize last states
        try:
            self._last_text = pyperclip.paste()
        except:
            self._last_text = ""
        
        try:
            self._last_image_hash = self._get_qimage_hash(QApplication.clipboard().image())
        except:
            self._last_image_hash = None

    def _get_qimage_hash(self, image: QImage):
        if image.isNull(): return None
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        return hash(buffer.data())

    def set_last_image_hash(self, image_hash):
        """Allows the main app to update the monitor's state directly."""
        self._last_image_hash = image_hash


    def check_clipboard(self):

        image_processed = False
        # 1. Prioritize checking for an image
        if self._config['history'].get('log_images', True):
            try:
                q_image = QApplication.clipboard().image()
                if not q_image.isNull():
                    current_image_hash = self._get_qimage_hash(q_image)
                    if current_image_hash != self._last_image_hash:
                        self._last_image_hash = current_image_hash
                        self._last_text = ""
                        
                        relative_path = os.path.join("images", f"img_{int(time.time() * 1000)}.png")
                        full_path = os.path.join(self.image_dir, os.path.basename(relative_path))
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        q_image.save(full_path, "PNG")
                        
                        self.new_entry.emit(relative_path, 'image')
                        image_processed = True
            except Exception:
                pass

        # 2. If no image was processed, check for text
        if not image_processed:
            try:
                current_text = pyperclip.paste()
                if current_text and current_text != self._last_text:
                    self._last_text = current_text
                    self._last_image_hash = None
                    self.new_entry.emit(current_text, 'text')
            except Exception:
                pass

    def _run(self):
        while not self._stopping:
            self._process_clipboard()
            time.sleep(1)

    def start(self):
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self._stopping = True