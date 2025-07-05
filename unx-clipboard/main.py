import sys
import os
import json
import traceback
import time
import shutil
from datetime import datetime
from threading import Thread

import pyperclip
from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt5.QtCore import QTimer, QProcess
from PyQt5.QtGui import QImage
import mss
import mss.tools
import pygetwindow as gw

from config import (
    DB_PATH, THEMES_PATH, IMAGES_PATH, CONFIG_FILE_PATH, 
    USER_DATA_DIR, USER_ICON_PATH, ICON_SOURCE_PATH
)
from core import Communication, Database, ClipboardMonitor
from ui import AppGUI, SnippingWidget, ScreenshotModeDialog, ImageEditorDialog
from system import SystemTrayIcon, HotkeyListener, startup_manager
from services import ImportExport, CloudSync, NotionIntegration

class ClipboardApp:
    def __init__(self):
        self._handle_first_run_setup()
        
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        self.comm = Communication()
        self.comm.hotkey_triggered.connect(self.toggle_window)
        self.comm.open_settings_requested.connect(self.open_settings)
        self.comm.snipping_tool_triggered.connect(self.start_snipping_tool)
        
        self.load_config()
        
        self.db = Database(DB_PATH, self.config)
        self.importer_exporter = ImportExport(self.db)
        self.notion_integrator = NotionIntegration(self.config)
        self.monitor = ClipboardMonitor(self._on_new_entry, self.config, IMAGES_PATH)
        
        hotkey_string = self.config.get('hotkey', '<ctrl>+<shift>+v')
        self.hotkey_listener = HotkeyListener(hotkey_string, self.comm.hotkey_triggered.emit)
        
        snipping_hotkey_string = self.config.get('snipping_hotkey', '<ctrl>+<shift>+s')
        self.snipping_hotkey_listener = HotkeyListener(snipping_hotkey_string, self.comm.snipping_tool_triggered.emit)
        
        self.gui = AppGUI(self.db, USER_ICON_PATH)
        self.cloud_syncer = CloudSync(self.config, self.db, self.gui)

        try:
            from PIL import Image
            tray_icon_image = Image.open(USER_ICON_PATH)
        except Exception as e:
            print(f"Could not load tray icon image: {e}")
            tray_icon_image = None

        app_callbacks = {
            'pin': self.pin_entry,
            'delete': self.delete_entry,
            'set_as_snippet': self.set_as_snippet,
            'remove_from_snippet': self.remove_from_snippet,
            'add_new_snippet': self.add_new_snippet,
            'copy_and_log_text': self.copy_and_log_text,
            'copy_item_to_clipboard': self.copy_item_to_clipboard,
            'edit_image': self.edit_image,
            'toggle_window': self.toggle_window,
            'exit': self.shutdown,
            'importer_exporter': self.importer_exporter,
            'manual_sync': self.manual_sync,
            'clear_history': self.clear_history,
            'notion_is_configured': self.notion_integrator.is_configured,
            'send_to_notion': self.send_to_notion,
            'get_config': lambda: self.config,
            'save_config': self.save_config,
            'set_startup_status': startup_manager.set_startup_status,
            'open_settings': self.open_settings,
            'start_snipping_tool': self.start_snipping_tool,
            'restart_app': self.restart_app,
            'copy_last_item': self.copy_last_item,
            'open_settings_requested': self.comm.open_settings_requested
        }

        self.gui.set_callbacks(app_callbacks)
        self.tray = SystemTrayIcon(app_callbacks, tray_icon_image)
        self.importer_exporter.parent = self.gui
        
        self.comm.new_entry_detected.connect(self.gui.refresh_list)
        self.comm.screenshot_taken_for_preview.connect(self.gui.update_screenshot_preview)
        
        self.setup_auto_sync_timer()
        
        self.apply_theme()
        
        if self.config.get('sync', {}).get('auto_sync', False):
            QTimer.singleShot(15000, self._trigger_startup_sync)

    def _handle_first_run_setup(self):
        os.makedirs(IMAGES_PATH, exist_ok=True)
        os.makedirs(THEMES_PATH, exist_ok=True)
        
        files_to_setup = {
            CONFIG_FILE_PATH: 'config.json',
            DB_PATH: 'clipboard_history.db',
            USER_ICON_PATH: 'icon.ico'
        }

        for dest_path, source_file in files_to_setup.items():
            if not os.path.exists(dest_path):
                source_path = resource_path(source_file)
                if os.path.exists(source_path):
                    try:
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(source_path, dest_path)
                    except Exception as e:
                        print(f"Error setting up {source_file}: {e}")
        
    def apply_theme(self):
        theme_name = self.config.get("theme", "System").lower()
        stylesheet = ""
        if theme_name in ["light", "dark"]:
            theme_path = os.path.join(THEMES_PATH, f"{theme_name}_theme.qss")
            if os.path.exists(theme_path):
                with open(theme_path, "r") as f: stylesheet = f.read()
        elif theme_name == "custom":
            ct = self.config.get('custom_theme', {})
            stylesheet = f"""QWidget {{ background-color: {ct.get('background', '#2e3440')}; color: {ct.get('foreground', '#d8dee9')}; font-family: "{ct.get('font_family', 'Segoe UI')}"; font-size: {ct.get('font_size', '10pt')};}} QListWidget, QLineEdit, QTextEdit, QSpinBox, QComboBox {{ background-color: {ct.get('background_light', '#3b4252')}; border: 1px solid {ct.get('accent_secondary', '#4c566a')}; }} QListWidget::item:selected {{ background-color: {ct.get('accent_primary', '#81a1c1')}; color: #2e3440;}} QPushButton {{ background-color: {ct.get('accent_secondary', '#4c566a')}; border: none; padding: 5px 10px; border-radius: 4px;}} QPushButton:hover {{ background-color: {ct.get('accent_primary', '#5e81ac')}; }}"""
        self.qt_app.setStyleSheet(stylesheet)

    def load_config(self):
        try:
            with open(CONFIG_FILE_PATH, 'r') as f: self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = {
                "history": {"retention_days": 30},
                "sync": {"auto_sync": False, "local_sync_path": ""},
                "hotkey": "<ctrl>+<shift>+v", "snipping_hotkey": "<ctrl>+<shift>+s", "theme": "System", 
                "custom_theme": {"background": "#2e3440", "foreground": "#d8dee9", "background_light": "#3b4252", "accent_primary": "#81a1c1", "accent_secondary": "#5e81ac", "font_family": "Segoe UI", "font_size": "10pt"},
                "notion": {"enabled": False, "api_key": "", "database_id": ""}
            }
            if not os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, 'w') as f: json.dump(self.config, f, indent=4)
            
    def save_config(self, config_data):
        self.config = config_data
        with open(CONFIG_FILE_PATH, 'w') as f: json.dump(self.config, f, indent=4)
        self.reload_config()

    def reload_config(self):
        self.load_config(); self.apply_theme()
        self.db.config = self.config
        self.db.apply_retention_policy()
        self.cloud_syncer = CloudSync(self.config, self.db, self.gui)
        self.notion_integrator = NotionIntegration(self.config)
        self.setup_auto_sync_timer(); self.gui.refresh_list()
    
    def manual_sync(self):
        if self.cloud_syncer: self.cloud_syncer.sync()

    def open_settings(self): self.gui.open_settings_dialog()
    
    def copy_item_to_clipboard(self, entry_id):
        entry = self.db.conn.execute("SELECT content, type FROM clipboard WHERE id=?", (entry_id,)).fetchone()
        if not entry: return
        content, content_type = entry
        self.monitor.ignore_next_change = True
        if content_type == 'text':
            pyperclip.copy(content)
        elif content_type == 'image':
            full_path = os.path.join(USER_DATA_DIR, content)
            q_image = QImage(full_path)
            if not q_image.isNull():
                QApplication.clipboard().setImage(q_image)

    def copy_and_log_text(self, text):
        self.db.add_entry(text, 'text')
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT id FROM clipboard ORDER BY id DESC LIMIT 1")
        res = cursor.fetchone()
        if res:
            new_id = res[0]
            self.copy_item_to_clipboard(new_id)
        self.gui.refresh_list()
        
    def clear_history(self): self.db.clear_history(); self.gui.refresh_list()
    def remove_from_snippet(self, entry_id): self.db.remove_from_snippet(entry_id); self.gui.refresh_list()
    def add_new_snippet(self, content): self.db.add_manual_snippet(content); self.gui.refresh_list()
    def set_as_snippet(self, entry_id): self.db.set_as_snippet(entry_id); self.gui.refresh_list()
    def copy_last_item(self):
        item = self.db.conn.execute("SELECT id FROM clipboard WHERE type='text' ORDER BY timestamp DESC LIMIT 1").fetchone()
        if item: self.copy_item_to_clipboard(item[0])

    def setup_auto_sync_timer(self):
        if hasattr(self, 'sync_timer') and self.sync_timer.isActive():
            self.sync_timer.stop()
        sync_config = self.config.get('sync', {})
        if sync_config.get('auto_sync', False):
            interval_ms = sync_config.get('sync_interval_minutes', 15) * 60 * 1000
            self.sync_timer = QTimer()
            self.sync_timer.timeout.connect(self._trigger_auto_sync)
            self.sync_timer.start(interval_ms)
            
    def _on_new_entry(self, content, content_type):
        if not self.config['history'].get('log_images', True) and content_type == 'image': return
        self.db.add_entry(content, content_type)
        self.comm.new_entry_detected.emit()
        
    def send_to_notion(self, entry_id):
        entry = self.db.conn.execute("SELECT content, type, timestamp FROM clipboard WHERE id=?", (entry_id,)).fetchone()
        if not entry: return
        success, message = self.notion_integrator.send_entry(*entry)
        if success: QMessageBox.information(self.gui, "Success", message)
        else: QMessageBox.critical(self.gui, "Notion Error", message)
        
    def pin_entry(self, entry_id): self.db.toggle_pin(entry_id); self.gui.refresh_list()
    
    def delete_entry(self, entry_id):
        cursor = self.db.conn.cursor(); cursor.execute("SELECT content, type FROM clipboard WHERE id = ?", (entry_id,)); result = cursor.fetchone()
        if result:
            content, content_type = result
            if content_type == 'image':
                image_path = os.path.join(USER_DATA_DIR, content)
                if os.path.exists(image_path):
                    try: os.remove(image_path)
                    except OSError as e: print(f"Error deleting image file {image_path}: {e}")
        self.db.delete_entry(entry_id); self.gui.refresh_list()
        
    def toggle_window(self):
        if self.gui.isVisible(): self.gui.hide()
        else: self.gui.show(); self.gui.activateWindow(); self.gui.raise_()
        
    def start_snipping_tool(self):
        self.gui.hide()
        QTimer.singleShot(200, self.launch_mode_dialog)

    def launch_mode_dialog(self):
        mode_dialog = self.gui.create_mode_dialog()
        if mode_dialog.exec_() == QDialog.Accepted:
            chosen_mode = mode_dialog.mode
            if chosen_mode == 'region':
                self.launch_region_snipper()
            elif chosen_mode == 'fullscreen':
                QTimer.singleShot(100, self.take_fullscreen_screenshot)
            elif chosen_mode == 'window':
                QTimer.singleShot(300, self.take_active_window_screenshot)
        else:
             self.gui.show()

    def launch_region_snipper(self):
        self.snipping_widget = self.gui.create_snipping_widget()
        self.snipping_widget.screenshot_taken.connect(self.log_screenshot_from_editor)
        self.snipping_widget.show()
        
    def take_fullscreen_screenshot(self):
        relative_path = os.path.join("images", f"ss_fullscreen_{int(time.time() * 1000)}.png")
        full_path = os.path.join(USER_DATA_DIR, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[1])
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=full_path)
        self.log_screenshot_from_editor(relative_path)

    def take_active_window_screenshot(self):
        try:
            active_window = gw.getActiveWindow()
            if active_window:
                monitor = { "top": active_window.top, "left": active_window.left, "width": active_window.width, "height": active_window.height }
                relative_path = os.path.join("images", f"ss_window_{int(time.time() * 1000)}.png")
                full_path = os.path.join(USER_DATA_DIR, relative_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with mss.mss() as sct:
                    sct_img = sct.grab(monitor)
                    mss.tools.to_png(sct_img.rgb, sct_img.size, output=full_path)
                self.log_screenshot_from_editor(relative_path)
            else:
                QMessageBox.warning(self.gui, "Capture Failed", "Could not find an active window.")
                self.gui.show()
        except Exception as e:
            print(f"Failed to capture active window: {e}")
            QMessageBox.warning(self.gui, "Capture Failed", f"An error occurred: {e}")
            self.gui.show()
        
    def log_screenshot_from_editor(self, image_path):
        full_path = os.path.join(USER_DATA_DIR, image_path)
        editor = self.gui.create_editor_widget(full_path)
        if editor.exec_() == QDialog.Accepted:
            self.db.add_entry(image_path, 'image')
            new_id = self.db.conn.execute("SELECT id FROM clipboard ORDER BY id DESC LIMIT 1").fetchone()[0]
            self.copy_item_to_clipboard(new_id)
            self.comm.screenshot_taken_for_preview.emit(full_path)
        else:
            try: os.remove(full_path)
            except OSError as e: print(f"Error deleting cancelled screenshot: {e}")
        self.gui.refresh_list()
        self.gui.show()
        
    def edit_image(self, entry_id):
        entry = self.db.conn.execute("SELECT content FROM clipboard WHERE id = ? AND type = 'image'", (entry_id,)).fetchone()
        if not entry: return
        image_path = entry[0]
        full_path = os.path.join(USER_DATA_DIR, image_path)
        if not os.path.exists(full_path):
            QMessageBox.warning(self.gui, "File Not Found", "The image file for this entry could not be found.")
            return
        editor = self.gui.create_editor_widget(full_path)
        if editor.exec_() == QDialog.Accepted:
            self.gui.refresh_list()
            self.comm.screenshot_taken_for_preview.emit(full_path)
        
    def restart_app(self):
        self.shutdown()
        QProcess.startDetached(sys.executable, sys.argv)
        
    def run(self):
        self.monitor.start(); self.tray.run(); self.hotkey_listener.start()
        self.snipping_hotkey_listener.start()
        self.gui.show(); sys.exit(self.qt_app.exec_())
        
    def shutdown(self):
        self.monitor.stop(); self.hotkey_listener.stop(); self.tray.stop()
        self.snipping_hotkey_listener.stop()
        self.db.close(); self.qt_app.quit()

    def _trigger_startup_sync(self):
        """A clean slot for the startup QTimer to connect to."""
        print("Performing sync on startup...")
        if self.cloud_syncer:
            Thread(target=self.cloud_syncer.sync, daemon=True).start()

if __name__ == "__main__":
    try:
        main_app = ClipboardApp()
        main_app.run()
    except Exception as e:
        app = QApplication(sys.argv)
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setText("A critical error occurred and UNX Clipboard must close.")
        error_dialog.setInformativeText(f"Error details: {e}\n\nTraceback:\n{traceback.format_exc()}")
        error_dialog.setWindowTitle("Fatal Error")
        error_dialog.exec_()
