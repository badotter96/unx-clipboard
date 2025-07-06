import sys
import os
import string
import secrets
import time
import math
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTextEdit,
    QLabel, QFrame, QSplitter, QStyle, QMessageBox, QAction, QFileDialog, QDialog,
    QMenu, QTabWidget, QInputDialog, QFormLayout, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QColorDialog, QDialogButtonBox, QFontComboBox, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QIcon, QImage, QFont, QColor, QPalette, QPainter, QBrush, QPen
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QTimer, QRect, QPoint, QBuffer
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile

from system import startup_manager
import mss
import mss.tools
from config import USER_DATA_DIR

class AuthDialog(QDialog):
    def __init__(self, auth_url, parent=None):
        super().__init__(parent)
        self.auth_url = auth_url
        self.setWindowTitle("Google Drive Authentication")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        instructions_label = QLabel("1. Copy URL & authorize in browser:")
        layout.addWidget(instructions_label)
        self.url_display = QTextEdit()
        self.url_display.setPlainText(self.auth_url)
        self.url_display.setReadOnly(True)
        self.url_display.setLineWrapMode(QTextEdit.WidgetWidth)
        self.url_display.setFixedHeight(100)
        layout.addWidget(self.url_display)
        copy_button = QPushButton("Copy URL")
        copy_button.clicked.connect(self.copy_url)
        layout.addWidget(copy_button, 0, Qt.AlignRight)
        code_label = QLabel("2. Paste authorization code here:")
        layout.addWidget(code_label)
        self.code_input = QLineEdit()
        layout.addWidget(self.code_input)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def copy_url(self):
        QApplication.clipboard().setText(self.auth_url)

    def get_code(self):
        return self.code_input.text()

class ThemeEditorDialog(QDialog):
    def __init__(self, theme_config, parent=None):
        super().__init__(parent)
        self.config = theme_config.copy()
        self.setWindowTitle("Custom Theme Editor")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.color_buttons = {}
        color_map = {
            'background': "Main Background", 'foreground': "Main Text",
            'background_light': "Lighter Background", 'accent_primary': "Primary Accent",
            'accent_secondary': "Secondary Accent"
        }
        for name, label in color_map.items():
            self.color_buttons[name] = self._create_color_button(name)
            form_layout.addRow(label, self.color_buttons[name])
        
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentText(self.config.get('font_family', 'Segoe UI'))
        form_layout.addRow("Font Family:", self.font_combo)
        
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 20)
        self.font_size_spinbox.setSuffix("pt")
        self.font_size_spinbox.setValue(int(self.config.get('font_size', '10pt')[:-2]))
        form_layout.addRow("Font Size:", self.font_size_spinbox)
        
        layout.addLayout(form_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_color_button(self, name):
        button = QPushButton()
        button.setFixedSize(100, 28)
        self._update_button_color(button, self.config.get(name, '#ffffff'))
        button.clicked.connect(lambda _, n=name, b=button: self.pick_color(n, b))
        return button

    def pick_color(self, name, button):
        color = QColorDialog.getColor(QColor(self.config.get(name)), self)
        if color.isValid():
            self.config[name] = color.name()
            self._update_button_color(button, color.name())

    def _update_button_color(self, button, color_hex):
        button.setText(color_hex)
        palette = button.palette()
        palette.setColor(QPalette.Button, QColor(color_hex))
        text_color = "#000000" if (QColor(color_hex).red()*0.299 + QColor(color_hex).green()*0.587 + QColor(color_hex).blue()*0.114) > 186 else "#ffffff"
        palette.setColor(QPalette.ButtonText, QColor(text_color))
        button.setPalette(palette)

    def get_updated_config(self):
        self.config['font_family'] = self.font_combo.currentText()
        self.config['font_size'] = f"{self.font_size_spinbox.value()}pt"
        return self.config

class SettingsDialog(QDialog):
    def __init__(self, config, callbacks, parent=None):
        super().__init__(parent)
        self.config = config
        self.app_callbacks = callbacks
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        # --- General Settings ---
        general_group = QGroupBox("General")
        general_layout = QFormLayout()
        self.startup_cb = QCheckBox("Run on system startup")
        self.startup_cb.setChecked(startup_manager.get_startup_status())
        note = " (Manual setup required on non-Windows systems)" if sys.platform != 'win32' else ""
        general_layout.addRow(f"Startup:{note}", self.startup_cb)
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)

        # --- Appearance Settings ---
        ui_group = QGroupBox("Appearance")
        ui_layout = QFormLayout()
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["System", "Light", "Dark", "Custom"])
        self.theme_selector.setCurrentText(self.config.get('theme', 'System'))
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(self.theme_selector)
        self.edit_theme_btn = QPushButton("Edit Custom Theme...")
        self.edit_theme_btn.clicked.connect(self.open_theme_editor)
        theme_layout.addWidget(self.edit_theme_btn)
        ui_layout.addRow("Theme:", theme_layout)
        ui_group.setLayout(ui_layout)
        layout.addWidget(ui_group)

        # --- History Settings ---
        history_group = QGroupBox("History")
        history_layout = QFormLayout()
        self.retention_days = QSpinBox()
        self.retention_days.setRange(0, 365)
        self.retention_days.setValue(self.config['history']['retention_days'])
        history_layout.addRow("Retention Days (0=forever):", self.retention_days)
        self.log_images_cb = QCheckBox()
        self.log_images_cb.setChecked(self.config['history'].get('log_images', True))
        history_layout.addRow("Log Copied Images:", self.log_images_cb)
        clear_history_btn = QPushButton("Clear Non-Essential History")
        clear_history_btn.clicked.connect(self.clear_history)
        history_layout.addRow(clear_history_btn)
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)

        # --- Cloud Sync Settings ---
        sync_group = QGroupBox("Cloud Sync")
        self.sync_layout = QFormLayout()
        
        # New "Last Sync" Label
        self.last_sync_label = QLabel("Never")
        self._update_last_sync_label()
        self.sync_layout.addRow("Last Successful Sync:", self.last_sync_label)
        
        self.auto_sync = QCheckBox()
        self.auto_sync.setChecked(self.config['sync']['auto_sync'])
        self.sync_layout.addRow("Enable Auto-Sync:", self.auto_sync)
        
        self.sync_interval = QSpinBox()
        self.sync_interval.setRange(1, 1440)
        self.sync_interval.setValue(self.config['sync'].get('sync_interval_minutes', 15))
        self.sync_layout.addRow("Auto-Sync Interval (minutes):", self.sync_interval)
        
        self.backup_retention = QSpinBox()
        self.backup_retention.setRange(0, 99)
        self.backup_retention.setToolTip("The number of recent backup files to keep. Set to 0 to disable.")
        self.backup_retention.setValue(self.config.get('sync', {}).get('backup_retention_count', 5))
        self.sync_layout.addRow("Backups to Keep (0=all):", self.backup_retention)
        
        self.sync_backend = QComboBox()
        self.sync_backend.addItems(["None", "LocalFolder"])
        self.sync_backend.setCurrentText(self.config['sync'].get('backend', 'None'))
        self.sync_backend.currentTextChanged.connect(self.update_sync_fields_visibility)
        self.sync_layout.addRow("Sync Backend:", self.sync_backend)
        
        self.local_sync_path_widget = QWidget()
        local_layout = QHBoxLayout(self.local_sync_path_widget)
        local_layout.setContentsMargins(0,0,0,0)
        self.local_sync_path_input = QLineEdit(self.config['sync'].get('local_sync_path', ''))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_for_folder)
        local_layout.addWidget(self.local_sync_path_input)
        local_layout.addWidget(browse_btn)
        self.sync_layout.addRow("Local Sync Path:", self.local_sync_path_widget)
        
        sync_group.setLayout(self.sync_layout)
        layout.addWidget(sync_group)
        self.update_sync_fields_visibility(self.sync_backend.currentText())

        # --- Discord Integration Settings ---
        discord_group = QGroupBox("Discord Integration")
        discord_layout = QFormLayout()
        self.discord_enabled_cb = QCheckBox("Send new clipboard items to Discord")
        self.discord_enabled_cb.setChecked(self.config.get('discord', {}).get('enabled', False))
        discord_layout.addRow(self.discord_enabled_cb)
        self.discord_webhook_input = QLineEdit(self.config.get('discord', {}).get('webhook_url', ''))
        self.discord_webhook_input.setPlaceholderText("Enter your Discord Webhook URL")
        discord_layout.addRow("Webhook URL:", self.discord_webhook_input)
        self.discord_text_thread_input = QLineEdit(self.config.get('discord', {}).get('text_thread_id', ''))
        self.discord_text_thread_input.setPlaceholderText("Enter the ID for the text thread")
        discord_layout.addRow("Text Thread ID:", self.discord_text_thread_input)
        self.discord_image_thread_input = QLineEdit(self.config.get('discord', {}).get('image_thread_id', ''))
        self.discord_image_thread_input.setPlaceholderText("Enter the ID for the image thread")
        discord_layout.addRow("Image Thread ID:", self.discord_image_thread_input)
        discord_group.setLayout(discord_layout)
        layout.addWidget(discord_group)

        # --- Dialog Buttons (Correctly placed at the bottom) ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_and_close)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _update_last_sync_label(self):
        """Reads the sync info file and updates the label text."""
        try:
            state_file = os.path.join(USER_DATA_DIR, 'last_sync_info.json')
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    data = json.load(f)
                    timestamp_iso = data.get("last_sync_timestamp")
                    if timestamp_iso:
                        dt_obj = datetime.fromisoformat(timestamp_iso)
                        self.last_sync_label.setText(dt_obj.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            print(f"Could not read last sync info: {e}")
            self.last_sync_label.setText("Error reading status")

    def open_theme_editor(self):
        editor = ThemeEditorDialog(self.config.get('custom_theme', {}), self)
        if editor.exec_() == QDialog.Accepted:
            self.config['custom_theme'] = editor.get_updated_config()
            self.theme_selector.setCurrentText("Custom")

    def update_sync_fields_visibility(self, text):
        is_local_folder = text.lower() == 'localfolder'
        self.sync_layout.labelForField(self.local_sync_path_widget).setVisible(is_local_folder)
        self.local_sync_path_widget.setVisible(is_local_folder)

    def save_and_close(self):
        self.app_callbacks['set_startup_status'](self.startup_cb.isChecked())
        self.config['theme'] = self.theme_selector.currentText()
        self.config['history']['retention_days'] = self.retention_days.value()
        self.config['history']['log_images'] = self.log_images_cb.isChecked()
        self.config['sync']['auto_sync'] = self.auto_sync.isChecked()
        self.config['sync']['sync_interval_minutes'] = self.sync_interval.value()
        self.config['sync']['backup_retention_count'] = self.backup_retention.value()
        self.config['sync']['backend'] = self.sync_backend.currentText()
        self.config['sync']['local_sync_path'] = self.local_sync_path_input.text()
        if 'discord' not in self.config:
            self.config['discord'] = {}
        self.config['discord']['enabled'] = self.discord_enabled_cb.isChecked()
        self.config['discord']['webhook_url'] = self.discord_webhook_input.text()
        self.config['discord']['text_thread_id'] = self.discord_text_thread_input.text()
        self.config['discord']['image_thread_id'] = self.discord_image_thread_input.text()
        self.app_callbacks['save_config'](self.config)
        self.accept()

    def clear_history(self):
        reply = QMessageBox.question(self, 'Confirm Clear', "Are you sure you want to delete all non-pinned and non-snippet history items? This cannot be undone.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.app_callbacks['clear_history']()

    def browse_for_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Sync Folder")
        if path:
            self.local_sync_path_input.setText(path)

class SurfingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        
        try:
            # Try to create a persistent, disk-based profile first.
            web_cache_path = os.path.join(USER_DATA_DIR, "web_cache")
            os.makedirs(web_cache_path, exist_ok=True)
            
            profile = QWebEngineProfile.defaultProfile()
            profile.setCachePath(web_cache_path)
            profile.setPersistentStoragePath(web_cache_path)
            
            print("Surfing tab is using a persistent disk cache.")
            self.browser = QWebEngineView() # Browser will use the default profile
        except Exception as e:
            # If creating the disk cache fails, fall back to an in-memory profile.
            print(f"Could not create disk cache: {e}. Falling back to in-memory profile.")
            # Using a new, non-default profile ensures it's off-the-record (in-memory).
            off_the_record_profile = QWebEngineProfile()
            self.browser = QWebEngineView()
            # Create a new page with the in-memory profile and set it on the browser.
            self.browser.setPage(QWebEnginePage(off_the_record_profile, self.browser))

        self.hibernation_timer = QTimer(self)
        self.hibernation_timer.setSingleShot(True)
        self.hibernation_timer.timeout.connect(self.hibernate_browser)
        
        # The browser will now automatically use the modified default profile
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl("https://www.google.com"))
        
        self.address_bar = QLineEdit()
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.addWidget(self.address_bar)
        
        self.back_action = QAction(self.style().standardIcon(QStyle.SP_ArrowBack), "Back", self)
        self.forward_action = QAction(self.style().standardIcon(QStyle.SP_ArrowForward), "Forward", self)
        self.refresh_action = QAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Refresh", self)
        
        self.address_bar.addAction(self.back_action, QLineEdit.LeadingPosition)
        self.address_bar.addAction(self.forward_action, QLineEdit.LeadingPosition)
        self.address_bar.addAction(self.refresh_action, QLineEdit.LeadingPosition)
        
        self.back_action.triggered.connect(self.browser.back)
        self.forward_action.triggered.connect(self.browser.forward)
        self.refresh_action.triggered.connect(self.browser.reload)
        
        self.address_bar.returnPressed.connect(self.navigate_to_url)
        self.browser.urlChanged.connect(self.update_address_bar)
        self.browser.page().action(QWebEnginePage.Back).changed.connect(self.update_nav_actions)
        self.browser.page().action(QWebEnginePage.Forward).changed.connect(self.update_nav_actions)
        
        self.update_nav_actions()
        layout.addLayout(nav_layout)
        layout.addWidget(self.browser)

    def navigate_to_url(self):
        url = QUrl.fromUserInput(self.address_bar.text())
        if url.isValid():
            self.browser.setUrl(url)

    def update_address_bar(self, url):
        self.address_bar.setText(url.toString())
        self.address_bar.setCursorPosition(0)

    def update_nav_actions(self):
        self.back_action.setEnabled(self.browser.page().action(QWebEnginePage.Back).isEnabled())
        self.forward_action.setEnabled(self.browser.page().action(QWebEnginePage.Forward).isEnabled())

    def hibernate_browser(self):
        if self.browser.url().toString() != "about:blank":
            print("Hibernating browser tab...")
            self.browser.setUrl(QUrl("about:blank"))

    def wake_browser(self):
        if self.hibernation_timer.isActive():
            self.hibernation_timer.stop()
        elif self.browser.url().toString() == "about:blank":
            print("Waking up browser tab...")
            self.navigate_to_url()

class PasswordGeneratorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.copy_callback = None
        main_layout = QVBoxLayout(self)
        output_group = QGroupBox("Generated Password")
        output_layout = QHBoxLayout(output_group)
        self.output_field = QLineEdit()
        self.output_field.setReadOnly(True)
        self.output_field.setFont(QFont("Courier New", 14))
        self.copy_btn = QPushButton()
        self.copy_btn.setIcon(self.style().standardIcon(QStyle.SP_ToolBarHorizontalExtensionButton))
        self.copy_btn.setToolTip("Copy to clipboard and add to history")
        self.copy_btn.clicked.connect(self.copy_password)
        output_layout.addWidget(self.output_field)
        output_layout.addWidget(self.copy_btn)
        main_layout.addWidget(output_group)
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        self.length_spinbox = QSpinBox()
        self.length_spinbox.setRange(8, 128)
        self.length_spinbox.setValue(16)
        self.uppercase_cb = QCheckBox("Include Uppercase Letters (A-Z)")
        self.uppercase_cb.setChecked(True)
        self.numbers_cb = QCheckBox("Include Numbers (0-9)")
        self.numbers_cb.setChecked(True)
        self.symbols_cb = QCheckBox("Include Symbols (!@#$%^&*)")
        self.symbols_cb.setChecked(True)
        options_layout.addRow("Password Length:", self.length_spinbox)
        options_layout.addRow(self.uppercase_cb)
        options_layout.addRow(self.numbers_cb)
        options_layout.addRow(self.symbols_cb)
        main_layout.addWidget(options_group)
        self.generate_btn = QPushButton("Generate Password")
        self.generate_btn.clicked.connect(self.generate_password)
        main_layout.addWidget(self.generate_btn)
        main_layout.addStretch()
        self.generate_password()

    def generate_password(self):
        length = self.length_spinbox.value()
        character_set = string.ascii_lowercase
        if self.uppercase_cb.isChecked():
            character_set += string.ascii_uppercase
        if self.numbers_cb.isChecked():
            character_set += string.digits
        if self.symbols_cb.isChecked():
            character_set += string.punctuation
        if not character_set:
            self.output_field.setText("Select at least one character type!")
            return
        password = ''.join(secrets.choice(character_set) for _ in range(length))
        self.output_field.setText(password)

    def copy_password(self):
        password = self.output_field.text()
        if password and self.copy_callback:
            self.copy_callback(password)

class SnippingWidget(QWidget):
    screenshot_taken = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        screen_geometry = QApplication.instance().primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.begin = None
        self.end = None

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setBrush(QBrush(QColor(0, 0, 0, 120)))
        qp.drawRect(self.rect())
        if self.begin and self.end:
            selection_rect = self.get_selection_rect()
            qp.setCompositionMode(QPainter.CompositionMode_Clear)
            qp.drawRect(selection_rect)

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.close()
        QTimer.singleShot(100, self.take_screenshot)

    def get_selection_rect(self):
        return QRect(self.begin, self.end).normalized()

    def take_screenshot(self):
        rect = self.get_selection_rect()
        screen_geo = QApplication.instance().primaryScreen().geometry()
        monitor = {"top": rect.top() + screen_geo.top(), "left": rect.left() + screen_geo.left(), "width": rect.width(), "height": rect.height()}
        
        relative_path = os.path.join("images", f"ss_{int(time.time() * 1000)}.png")
        
        full_path = os.path.join(USER_DATA_DIR, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=full_path)
            
        self.screenshot_taken.emit(relative_path)

class ScreenshotModeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = None
        self.setWindowTitle("Choose Capture Mode")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        label = QLabel("Select screenshot type:")
        layout.addWidget(label)
        
        button_layout = QHBoxLayout()
        
        self.region_button = QPushButton("Capture Region")
        self.region_button.clicked.connect(self.select_region)
        button_layout.addWidget(self.region_button)
        
        self.fullscreen_button = QPushButton("Capture Fullscreen")
        self.fullscreen_button.clicked.connect(self.select_fullscreen)
        button_layout.addWidget(self.fullscreen_button)

        self.window_button = QPushButton("Capture Window")
        self.window_button.clicked.connect(self.select_window)
        button_layout.addWidget(self.window_button)
        
        layout.addLayout(button_layout)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button, 0, Qt.AlignCenter)
        
        screen_geo = QApplication.primaryScreen().geometry()
        self.adjustSize()
        self.move(int((screen_geo.width() - self.width()) / 2), 50)

    def select_region(self):
        self.mode = 'region'
        self.accept()

    def select_fullscreen(self):
        self.mode = 'fullscreen'
        self.accept()

    def select_window(self):
        self.mode = 'window'
        self.accept()

class DrawingCanvas(QWidget):
    crop_area_selected = pyqtSignal()
    undo_stack_changed = pyqtSignal()

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        
        self.base_pixmap = QPixmap(image_path)
        self.drawing_pixmap = QPixmap(self.base_pixmap.size())
        self.drawing_pixmap.fill(Qt.transparent)
        
        self.preview_pixmap = QPixmap(self.base_pixmap.size())
        self.preview_pixmap.fill(Qt.transparent)

        self.last_pos = None
        self.start_pos = None
        self.crop_rect = None
        self.tool = 'pen'
        self.pen_color = QColor(Qt.red)
        self.pen_thickness = 3

        self.undo_stack = [(self.drawing_pixmap.copy(), self.base_pixmap.copy())]
        self.redo_stack = []
        
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        widget_rect = self.rect()
        
        display_pixmap = self.base_pixmap.copy()
        temp_painter = QPainter(display_pixmap)
        temp_painter.drawPixmap(0, 0, self.drawing_pixmap)
        temp_painter.end()

        scaled_pixmap = display_pixmap.scaled(widget_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        x = int((widget_rect.width() - scaled_pixmap.width()) / 2)
        y = int((widget_rect.height() - scaled_pixmap.height()) / 2)
        
        self.target_rect = QRect(x, y, scaled_pixmap.width(), scaled_pixmap.height())
        
        painter.drawPixmap(self.target_rect, scaled_pixmap)
        
        if not self.preview_pixmap.isNull():
            painter.drawPixmap(self.target_rect, self.preview_pixmap)

    def _map_widget_to_pixmap(self, widget_pos):
        if not hasattr(self, 'target_rect') or not self.target_rect.contains(widget_pos):
            return None
        
        relative_x = widget_pos.x() - self.target_rect.x()
        relative_y = widget_pos.y() - self.target_rect.y()
        
        if self.target_rect.width() == 0 or self.target_rect.height() == 0:
            return None

        pixmap_x = (relative_x * self.base_pixmap.width()) / self.target_rect.width()
        pixmap_y = (relative_y * self.base_pixmap.height()) / self.target_rect.height()

        return QPoint(int(pixmap_x), int(pixmap_y))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = self._map_widget_to_pixmap(event.pos())
            if pos:
                self.start_pos = pos
                self.last_pos = pos
                # Save state on new stroke/shape
                if self.tool in ['pen', 'highlighter', 'rect']:
                    self.add_undo_state()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.last_pos:
            current_pos = self._map_widget_to_pixmap(event.pos())
            if current_pos:
                if self.tool in ['pen', 'highlighter']:
                    self.draw_line_to(current_pos)
                elif self.tool in ['rect', 'crop']:
                    self.draw_preview_shape(current_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos:
            end_pos = self._map_widget_to_pixmap(event.pos())
            if end_pos:
                if self.tool == 'rect':
                    self.preview_pixmap.fill(Qt.transparent)
                    self.draw_final_shape(end_pos)
                elif self.tool == 'crop':
                    self.crop_rect = QRect(self.start_pos, end_pos).normalized()
                    self.crop_area_selected.emit()
            
            self.start_pos = None
            self.last_pos = None

    def draw_line_to(self, end_pos):
        painter = QPainter(self.drawing_pixmap)
        pen = QPen(self.pen_color, self.pen_thickness, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if self.tool == 'highlighter':
            color = QColor(self.pen_color)
            color.setAlpha(100)
            pen.setColor(color)
            pen.setWidth(15)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(pen)
        painter.drawLine(self.last_pos, end_pos)
        self.last_pos = end_pos
        self.update()

    def draw_preview_shape(self, end_pos):
        self.preview_pixmap.fill(Qt.transparent)
        painter = QPainter(self.preview_pixmap)
        pen = QPen(self.pen_color, self.pen_thickness, Qt.DashLine if self.tool == 'crop' else Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(QRect(self.start_pos, end_pos))
        self.update()

    def draw_final_shape(self, end_pos):
        painter = QPainter(self.drawing_pixmap)
        pen = QPen(self.pen_color, self.pen_thickness, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(QRect(self.start_pos, end_pos))
        self.update()
        
    def apply_crop(self):
        if not self.crop_rect: return
        
        self.add_undo_state()
        
        combined_pixmap = self.base_pixmap.copy()
        painter = QPainter(combined_pixmap)
        painter.drawPixmap(0,0, self.drawing_pixmap)
        painter.end()

        self.base_pixmap = combined_pixmap.copy(self.crop_rect)
        
        self.drawing_pixmap = QPixmap(self.base_pixmap.size())
        self.drawing_pixmap.fill(Qt.transparent)

        self.preview_pixmap.fill(Qt.transparent)
        self.crop_rect = None
        self.update()
        
    def set_tool(self, tool_name):
        self.tool = tool_name
        self.crop_rect = None
        self.preview_pixmap.fill(Qt.transparent)
        self.update()

    def set_pen_color(self, color):
        self.pen_color = color

    def add_undo_state(self):
        self.undo_stack.append((self.drawing_pixmap.copy(), self.base_pixmap.copy()))
        self.redo_stack.clear()
        self.undo_stack_changed.emit()

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            drawing_state, base_state = self.undo_stack[-1]
            self.drawing_pixmap = drawing_state.copy()
            self.base_pixmap = base_state.copy()
            self.update()
            self.undo_stack_changed.emit()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.redo_stack.pop())
            drawing_state, base_state = self.undo_stack[-1]
            self.drawing_pixmap = drawing_state.copy()
            self.base_pixmap = base_state.copy()
            self.update()
            self.undo_stack_changed.emit()

class ImageEditorDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle("Edit Screenshot")
        self.setWindowState(Qt.WindowMaximized)
        main_layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        main_layout.addLayout(toolbar)

        self.btn_draw = QPushButton("Draw")
        self.btn_draw.setCheckable(True)
        self.btn_draw.setChecked(True)
        self.btn_draw.clicked.connect(lambda: self.set_tool('pen'))
        
        self.btn_highlight = QPushButton("Highlight")
        self.btn_highlight.setCheckable(True)
        self.btn_highlight.clicked.connect(lambda: self.set_tool('highlighter'))
        
        self.btn_rect = QPushButton("Outline")
        self.btn_rect.setCheckable(True)
        self.btn_rect.clicked.connect(lambda: self.set_tool('rect'))

        self.btn_crop = QPushButton("Crop")
        self.btn_crop.setCheckable(True)
        self.btn_crop.clicked.connect(lambda: self.set_tool('crop'))
        
        self.btn_color = QPushButton("Color")
        self.btn_color.clicked.connect(self.pick_color)
        
        self.btn_apply_crop = QPushButton("Apply Crop")
        self.btn_apply_crop.hide()
        self.btn_apply_crop.clicked.connect(self.apply_crop_action)

        toolbar.addWidget(self.btn_draw)
        toolbar.addWidget(self.btn_highlight)
        toolbar.addWidget(self.btn_color)
        toolbar.addWidget(self.btn_rect)
        toolbar.addWidget(self.btn_crop)
        toolbar.addWidget(self.btn_apply_crop)
        toolbar.addStretch()

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.clicked.connect(self.undo_action)
        toolbar.addWidget(self.btn_undo)
        self.btn_redo = QPushButton("Redo")
        self.btn_redo.clicked.connect(self.redo_action)
        toolbar.addWidget(self.btn_redo)

        self.canvas = DrawingCanvas(self.image_path, self)
        self.canvas.crop_area_selected.connect(lambda: self.btn_apply_crop.show())
        self.canvas.undo_stack_changed.connect(self.update_button_states)
        main_layout.addWidget(self.canvas, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_image)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.update_button_states()

    def set_tool(self, tool_name):
        self.btn_draw.setChecked(tool_name == 'pen')
        self.btn_highlight.setChecked(tool_name == 'highlighter')
        self.btn_rect.setChecked(tool_name == 'rect')
        self.btn_crop.setChecked(tool_name == 'crop')
        self.btn_apply_crop.hide()
        self.canvas.set_tool(tool_name)
    
    def pick_color(self):
        color = QColorDialog.getColor(self.canvas.pen_color)
        if color.isValid():
            self.canvas.set_pen_color(color)

    def undo_action(self):
        self.canvas.undo()

    def redo_action(self):
        self.canvas.redo()

    def update_button_states(self):
        self.btn_undo.setEnabled(len(self.canvas.undo_stack) > 1)
        self.btn_redo.setEnabled(len(self.canvas.redo_stack) > 0)
    
    def apply_crop_action(self):
        self.canvas.apply_crop()
        self.set_tool('pen')

    def save_image(self):
        final_pixmap = self.canvas.base_pixmap.copy()
        painter = QPainter(final_pixmap)
        painter.drawPixmap(0, 0, self.canvas.drawing_pixmap)
        painter.end()
        final_pixmap.save(self.image_path, "PNG")
        self.accept()

class AppGUI(QMainWindow):
    def __init__(self, db, icon_path):
        super().__init__()
        self.db = db
        self.app_callbacks = {}
        self.importer_exporter = None
        self.notion_is_configured = False
        self.settings_dialog = None
        
        self.setWindowTitle("UNX Clipboard")
        self.setGeometry(100, 100, 700, 800)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.create_widgets()
        self.current_page = 1
        self.total_pages = 1
        self.items_per_page = 100
        
    def set_callbacks(self, callbacks):
        self.app_callbacks = callbacks
        self.importer_exporter = self.app_callbacks['importer_exporter']
        self.notion_is_configured = self.app_callbacks['notion_is_configured']()
        self.create_menu()
        self.populate_all_lists()
        self.password_widget.copy_callback = self.app_callbacks['copy_and_log_text']
        self.snipping_widget_button.clicked.connect(self.app_callbacks['start_snipping_tool'])

    def create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('&File')
        
        # --- Simplified Menu ---
        backup_action = QAction('Create Full Backup...', self)
        backup_action.triggered.connect(self.create_full_backup)
        file_menu.addAction(backup_action)
        
        restore_action = QAction('Restore from Backup...', self)
        restore_action.triggered.connect(self.restore_from_backup)
        file_menu.addAction(restore_action)
        
        file_menu.addSeparator()
        exit_action = QAction('&Exit', self)
        exit_action.triggered.connect(self.app_callbacks['exit'])
        file_menu.addAction(exit_action)
        
        # --- Other Menus ---
        sync_menu = menu_bar.addMenu('&Sync')
        manual_sync = QAction('Run Manual Sync', self)
        manual_sync.triggered.connect(self.app_callbacks['manual_sync'])
        sync_menu.addAction(manual_sync)
        
        settings_menu = menu_bar.addMenu('&Settings')
        configure = QAction('Configure...', self)
        configure.triggered.connect(self.open_settings_dialog)
        settings_menu.addAction(configure)
        
        help_menu = menu_bar.addMenu('&Help')
        about = QAction('About UNX Clipboard', self)
        about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about)
        
    def show_about_dialog(self):
        QMessageBox.about(self, "About UNX Clipboard", "<h3>UNX Clipboard</h3><p>A powerful, feature-rich clipboard manager.</p>")
        
    def open_settings_dialog(self):
        self.settings_dialog = SettingsDialog(self.app_callbacks['get_config'](), self.app_callbacks, self)
        self.settings_dialog.exec_()
        
    def open_new_snippet_dialog(self):
        text, ok = QInputDialog.getMultiLineText(self, "New Snippet", "Enter text:")
        if ok and text:
            self.app_callbacks['add_new_snippet'](text)
            
    def create_snipping_widget(self):
        return SnippingWidget(self)
        
    def create_mode_dialog(self):
        return ScreenshotModeDialog(self)
        
    def create_editor_widget(self, image_path):
        return ImageEditorDialog(image_path, self)
        
    def create_full_backup(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Create Full Backup", "", "UNX Backup Files (*.unxbackup)")
        if filepath:
            self.app_callbacks['importer_exporter'].export_full_backup(filepath)
            
    def restore_from_backup(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Restore from Backup", "", "UNX Backup Files (*.unxbackup *.zip)")
        if filepath:
            if self.app_callbacks['importer_exporter'].import_full_backup(filepath):
                self.app_callbacks['restart_app']()
    
    def update_pagination_controls(self):
        """Updates the page label and enables/disables the prev/next buttons."""
        self.page_label.setText(f"Page {self.current_page} / {self.total_pages}")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < self.total_pages)

    def on_search_changed(self):
        """Resets to the first page whenever the search text changes."""
        self.current_page = 1
        self.populate_all_lists()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.populate_all_lists()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.populate_all_lists()

    def create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Clipboard History...")
        self.search_input.textChanged.connect(self.on_search_changed)
        main_layout.addWidget(self.search_input)
        
        main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(main_splitter)
        
        top_pane = QWidget()
        top_pane.setMinimumHeight(0)
        top_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top_layout = QVBoxLayout(top_pane)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.main_tabs = QTabWidget()
        top_layout.addWidget(self.main_tabs)
        
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        self.tabs = QTabWidget()
        self.list_widgets = {}
        tab_names = ["All", "Text", "Images", "Pinned", "Snippets"]
        for name in tab_names:
            list_widget = QListWidget()
            list_widget.currentItemChanged.connect(self.on_item_select)
            list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(self.show_item_context_menu)
            self.tabs.addTab(list_widget, name)
            self.list_widgets[name] = list_widget
        history_layout.addWidget(self.tabs)

        pagination_layout = QHBoxLayout()
        self.prev_page_button = QPushButton("<< Previous")
        self.prev_page_button.clicked.connect(self.prev_page)
        
        self.page_label = QLabel("Page 1 / 1")
        self.page_label.setAlignment(Qt.AlignCenter)
        
        self.next_page_button = QPushButton("Next >>")
        self.next_page_button.clicked.connect(self.next_page)
        
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.next_page_button)
        history_layout.addLayout(pagination_layout)
        
        self.action_buttons_widget = QWidget()
        button_layout = QHBoxLayout(self.action_buttons_widget)
        self.new_snippet_button = QPushButton("New Snippet")
        self.new_snippet_button.clicked.connect(self.open_new_snippet_dialog)
        button_layout.addWidget(self.new_snippet_button)
        self.pin_button = QPushButton("Pin/Unpin")
        self.pin_button.clicked.connect(lambda: self.perform_action_on_selected('pin'))
        button_layout.addWidget(self.pin_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(lambda: self.perform_action_on_selected('delete'))
        button_layout.addWidget(self.delete_button)
        history_layout.addWidget(self.action_buttons_widget)
        
        self.surfing_widget = SurfingWidget()
        self.password_widget = PasswordGeneratorWidget()
        
        snipping_tab_widget = QWidget()
        snipping_layout = QVBoxLayout(snipping_tab_widget)
        
        self.screenshot_preview_label = QLabel("Last screenshot will be shown here")
        self.screenshot_preview_label.setAlignment(Qt.AlignCenter)
        self.screenshot_preview_label.setFrameShape(QFrame.StyledPanel)
        snipping_layout.addWidget(self.screenshot_preview_label, 1)
        
        screenshot_action_group = QGroupBox()
        screenshot_action_layout = QVBoxLayout(screenshot_action_group)
        snipping_info_label = QLabel("Press the button below or use the global hotkey (default: Ctrl+Shift+S) to take a screenshot.")
        snipping_info_label.setWordWrap(True)
        snipping_info_label.setAlignment(Qt.AlignCenter)
        self.snipping_widget_button = QPushButton("Launch Screenshot Tool")
        screenshot_action_layout.addWidget(snipping_info_label)
        screenshot_action_layout.addWidget(self.snipping_widget_button, 0, Qt.AlignCenter)
        snipping_layout.addWidget(screenshot_action_group)

        self.main_tabs.addTab(history_widget, "Clipboard")
        self.main_tabs.addTab(self.surfing_widget, "Surfing")
        self.main_tabs.addTab(self.password_widget, "Password Generator")
        self.main_tabs.addTab(snipping_tab_widget, "Screenshot")
        main_splitter.addWidget(top_pane)
        
        bottom_pane = QFrame()
        bottom_pane.setFrameShape(QFrame.StyledPanel)
        bottom_pane.setMinimumHeight(0)
        bottom_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bottom_layout = QVBoxLayout(bottom_pane)
        self.preview_label = QLabel("Select a clipboard item to see a preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        bottom_layout.addWidget(self.preview_label)
        bottom_layout.addWidget(self.preview_text)
        self.preview_text.hide()
        main_splitter.addWidget(bottom_pane)
        main_splitter.setSizes([500, 300])
        main_splitter.setHandleWidth(10)
        main_splitter.setChildrenCollapsible(False)
        
        self.main_tabs.currentChanged.connect(self.on_main_tab_changed)
        self.on_main_tab_changed(0) 

    def update_screenshot_preview(self, image_path):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.screenshot_preview_label.setText("Could not load preview.")
        else:
            scaled_pixmap = pixmap.scaled(
                self.screenshot_preview_label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            self.screenshot_preview_label.setPixmap(scaled_pixmap)

    def on_main_tab_changed(self, index):
        is_clipboard_tab = self.main_tabs.tabText(index) == "Clipboard"
        self.search_input.setVisible(is_clipboard_tab)
        self.action_buttons_widget.setVisible(is_clipboard_tab)
        self.tabs.setVisible(is_clipboard_tab)
        self.main_tabs.parent().parent().widget(1).setVisible(is_clipboard_tab)
        
        surfing_widget_index = -1
        for i in range(self.main_tabs.count()):
            if isinstance(self.main_tabs.widget(i), SurfingWidget):
                surfing_widget_index = i
                break
        
        if surfing_widget_index != -1:
            if index == surfing_widget_index:
                self.surfing_widget.wake_browser()
            else:
                self.surfing_widget.hibernation_timer.start(60000)

    def get_current_list_widget(self):
        return self.tabs.widget(self.tabs.currentIndex())

    def show_item_context_menu(self, position):
        active_list_widget = self.get_current_list_widget()
        if not active_list_widget: return
        item = active_list_widget.itemAt(position)
        if not item: return
        
        entry_id = item.data(Qt.UserRole)
        entry = self.db.conn.execute("SELECT type, is_snippet FROM clipboard WHERE id = ?", (entry_id,)).fetchone()
        if not entry: return
        
        content_type, is_a_snippet = entry
        
        context_menu = QMenu(self)
        copy_action = context_menu.addAction("Copy Content")
        
        edit_action = None
        if content_type == 'image':
            edit_action = context_menu.addAction("Edit Image")

        pin_action = context_menu.addAction("Pin/Unpin Item")
        snippet_text = "Remove from Snippets" if is_a_snippet else "Add to Snippets"
        snippet_action = context_menu.addAction(snippet_text)
        
        context_menu.addSeparator()
        delete_action = context_menu.addAction("Delete Item")
        
        action = context_menu.exec_(active_list_widget.mapToGlobal(position))
        
        if action == copy_action: self.app_callbacks['copy_item_to_clipboard'](entry_id)
        elif action == edit_action: self.app_callbacks['edit_image'](entry_id)
        elif action == pin_action: self.app_callbacks['pin'](entry_id)
        elif action == snippet_action:
            if is_a_snippet: self.app_callbacks['remove_from_snippet'](entry_id)
            else: self.app_callbacks['set_as_snippet'](entry_id)
        elif action == delete_action: self.app_callbacks['delete'](entry_id)

    def populate_all_lists(self):
        if not self.app_callbacks: return
        for lw in self.list_widgets.values(): lw.clear()
        
        search_text = self.search_input.text()
        
        # First, get the total count of items that match the search
        total_items = self.db.get_total_entry_count(search_text=search_text)
        if total_items == 0:
            self.total_pages = 1 # At least one page, even if empty
        else:
            self.total_pages = math.ceil(total_items / self.items_per_page)

        # Now, get only the items for the current page
        all_entries = self.db.get_all_entries(
            search_text=search_text, 
            page=self.current_page, 
            per_page=self.items_per_page
        )
        
        for entry_id, content, content_type, timestamp, pinned, is_snippet in all_entries:
            pin_char = "📌" if pinned else " "; snippet_char = "🔖" if is_snippet else ""
            display_text = content.replace('\n', ' ').strip()
            if len(display_text) > 60: display_text = display_text[:57] + "..."
            list_item_text = f"{pin_char}{snippet_char} [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {display_text}"
            all_item = QListWidgetItem(list_item_text); all_item.setData(Qt.UserRole, entry_id)
            
            # This logic remains the same, but now only shows one page of items
            self.list_widgets["All"].addItem(all_item)
            if content_type == 'text': self.list_widgets["Text"].addItem(all_item.clone())
            elif content_type == 'image': self.list_widgets["Images"].addItem(all_item.clone())
            if pinned: self.list_widgets["Pinned"].addItem(all_item.clone())
            if is_snippet: self.list_widgets["Snippets"].addItem(all_item.clone())
            
        self.update_pagination_controls()

    def on_item_select(self, current_item, previous_item=None):
        if not current_item:
            self.preview_text.hide()
            self.preview_label.setText("Select a clipboard item to see a preview")
            self.preview_label.show()
            return
        entry_id = current_item.data(Qt.UserRole)
        entry = self.db.conn.execute("SELECT content, type FROM clipboard WHERE id = ?", (entry_id,)).fetchone()
        if not entry:
            return
        content, content_type = entry
        self.preview_text.hide()
        self.preview_label.show()
        if content_type == 'text':
            self.preview_label.hide()
            self.preview_text.setText(content)
            self.preview_text.show()
        elif content_type == 'image':
            full_path = os.path.join(USER_DATA_DIR, content)
            pixmap = QPixmap(full_path)
            if pixmap.isNull():
                self.preview_label.setText(f"Image not found:\n{content}")
            else:
                scaled_pixmap = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled_pixmap)
                
    def perform_action_on_selected(self, action_name):
        active_list_widget = self.get_current_list_widget()
        item = active_list_widget.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.UserRole)
        if entry_id:
            self.app_callbacks[action_name](entry_id)
            
    def refresh_list(self):
        self.populate_all_lists()
        
    def closeEvent(self, event):
        event.ignore()
        self.hide()