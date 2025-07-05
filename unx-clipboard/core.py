import sqlite3
import os
import time
from datetime import datetime, timedelta
from PyQt5.QtCore import QObject, pyqtSignal, QBuffer, QThread
from PyQt5.QtGui import QImage
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

class Database:
    def __init__(self, db_path, config):
        self.db_path = db_path
        self.config = config
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA cache_size = -4000;")
        self.conn.execute("PRAGMA temp_store = MEMORY;")
        self.create_table()
    def re_init(self):
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
    def create_table(self):
        with self.conn:
            try:
                self.conn.execute("ALTER TABLE clipboard ADD COLUMN is_snippet INTEGER DEFAULT 0")
            except sqlite3.OperationalError: pass
            self.conn.execute("""CREATE TABLE IF NOT EXISTS clipboard (id INTEGER PRIMARY KEY, content TEXT NOT NULL, type TEXT NOT NULL, timestamp TIMESTAMP NOT NULL, pinned INTEGER DEFAULT 0, is_snippet INTEGER DEFAULT 0)""")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON clipboard (content);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON clipboard (timestamp);")
    def add_entry(self, content, content_type):
        with self.conn:
            self.conn.execute("INSERT INTO clipboard (content, type, timestamp) VALUES (?, ?, ?)", (content, content_type, datetime.now()))
    def add_manual_snippet(self, content):
        with self.conn: self.conn.execute("INSERT INTO clipboard (content, type, timestamp, is_snippet) VALUES (?, 'text', ?, 1)", (content, datetime.now()))
    def get_total_entry_count(self, search_text=""):
        query = "SELECT COUNT(*) FROM clipboard"
        params = []
        if search_text:
            query += " WHERE content LIKE ?"
            params.append(f"%{search_text}%")
        cursor = self.conn.execute(query, params)
        count = cursor.fetchone()[0]
        return count
    def get_all_entries(self, search_text="", page=1, per_page=100):
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
            cursor = self.conn.execute("SELECT pinned FROM clipboard WHERE id = ?", (entry_id,)); current_status = cursor.fetchone()[0]
            self.conn.execute("UPDATE clipboard SET pinned = ? WHERE id = ?", (1 - current_status, entry_id))
    def set_as_snippet(self, entry_id):
        with self.conn: self.conn.execute("UPDATE clipboard SET is_snippet = 1 WHERE id = ?", (entry_id,))
    def remove_from_snippet(self, entry_id):
        with self.conn: self.conn.execute("UPDATE clipboard SET is_snippet = 0 WHERE id = ?", (entry_id,))
    def delete_entry(self, entry_id):
        with self.conn: self.conn.execute("DELETE FROM clipboard WHERE id = ?", (entry_id,))
    def apply_retention_policy(self):
        retention_days = self.config['history']['retention_days']
        if retention_days > 0:
            cutoff = datetime.now() - timedelta(days=retention_days)
            with self.conn: self.conn.execute("DELETE FROM clipboard WHERE pinned = 0 AND is_snippet = 0 AND timestamp < ?", (cutoff,))
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
                if os.path.exists(full_path): os.remove(full_path)
            except Exception as e: print(f"Could not delete image file {relative_path}: {e}")
    def close(self): self.conn.close()

class ClipboardMonitor:
    def __init__(self, callback, config, images_path):
        self._callback = callback; self._config = config; self.image_dir = images_path
        self._stopping = False; self._last_text = ""; self._last_image_hash = None
        self.ignore_next_change = False
        try: self._last_text = pyperclip.paste()
        except: self._last_text = ""
        try: self._last_image_hash = self._get_image_hash(ImageGrab.grabclipboard())
        except: self._last_image_hash = None
    def _get_image_hash(self, image):
        if image is None: return None
        if isinstance(image, QImage):
            buffer = QBuffer(); buffer.open(QBuffer.ReadWrite); image.save(buffer, "PNG"); return hash(buffer.data())
        elif isinstance(image, Image.Image): return hash(image.tobytes())
        return None
    def _process_clipboard(self):
        if self.ignore_next_change:
            self.ignore_next_change = False
            try: self._last_text = pyperclip.paste()
            except: self._last_text = ""
            try: self._last_image_hash = self._get_image_hash(ImageGrab.grabclipboard())
            except: self._last_image_hash = None
            return
        if self._config['history'].get('log_images', True):
            try:
                image = ImageGrab.grabclipboard()
                if isinstance(image, Image.Image):
                    current_image_hash = self._get_image_hash(image)
                    if current_image_hash != self._last_image_hash:
                        self._last_image_hash = current_image_hash
                        relative_path = os.path.join("images", f"img_{int(time.time() * 1000)}.png")
                        full_path = os.path.join(self.image_dir, os.path.basename(relative_path))
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        image.save(full_path, "PNG")
                        self._callback(relative_path, 'image')
                        self._last_text = ""
                        return
            except Exception: pass
        try:
            current_text = pyperclip.paste()
            if current_text and current_text != self._last_text:
                self._last_text = current_text
                self._last_image_hash = None
                self._callback(current_text, 'text')
        except Exception: pass
    def _run(self):
        while not self._stopping: self._process_clipboard(); time.sleep(1)
    def start(self): self.thread = Thread(target=self._run, daemon=True); self.thread.start()
    def stop(self): self._stopping = True

class DataLoader(QObject):
    results_ready = pyqtSignal(list, int)
    def __init__(self, db, search_text, current_page, items_per_page):
        super().__init__()
        self.db = db
        self.search_text = search_text
        self.current_page = current_page
        self.items_per_page = items_per_page
    def run(self):
        total_count = self.db.get_total_entry_count(self.search_text)
        entries = self.db.get_all_entries(self.search_text, self.current_page, self.items_per_page)
        self.results_ready.emit(entries, total_count)