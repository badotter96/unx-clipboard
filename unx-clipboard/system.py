import sys
import os
from threading import Thread
from pynput import keyboard
from PIL import Image
from pystray import Icon as TrayIcon, Menu, MenuItem

class StartupManager:
    APP_NAME = "UNX Clipboard"

    def get_command(self):
        """Gets the command needed to run the application."""
        # For development, command is "python /path/to/main.py"
        # For packaged app, command is just "/path/to/executable"
        if getattr(sys, 'frozen', False):
            return f'"{sys.executable}"'
        else:
            return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'

    def _get_plist_path(self):
        return os.path.expanduser(f'~/Library/LaunchAgents/com.unx-clipboard.app.plist')

    def _get_desktop_file_path(self):
        return os.path.expanduser('~/.config/autostart/unx-clipboard.desktop')

    def set_startup_status(self, should_startup):
        """Adds or removes the application from OS-specific startup lists."""
        if sys.platform == 'win32':
            self._set_startup_windows(should_startup)
        elif sys.platform == 'darwin':
            self._set_startup_macos(should_startup)
        elif sys.platform.startswith('linux'):
            self._set_startup_linux(should_startup)

    def get_startup_status(self):
        """Checks if the application is set to run on startup."""
        if sys.platform == 'win32':
            return self._get_startup_windows()
        elif sys.platform == 'darwin':
            return self._get_startup_macos()
        elif sys.platform.startswith('linux'):
            return self._get_startup_linux()
        return False

    # --- Windows Specific ---
    def _set_startup_windows(self, should_startup):
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.HKEY_CURRENT_USER
        try:
            with winreg.OpenKey(key, key_path, 0, winreg.KEY_ALL_ACCESS) as reg_key:
                if should_startup:
                    winreg.SetValueEx(reg_key, self.APP_NAME, 0, winreg.REG_SZ, self.get_command())
                else:
                    winreg.DeleteValue(reg_key, self.APP_NAME)
        except FileNotFoundError:
            if should_startup:
                try:
                    with winreg.CreateKey(key, key_path) as reg_key:
                        winreg.SetValueEx(reg_key, self.APP_NAME, 0, winreg.REG_SZ, self.get_command())
                except OSError as e:
                    print(f"Error creating startup key: {e}")
        except Exception as e:
            print(f"Error accessing startup registry: {e}")

    def _get_startup_windows(self):
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, self.APP_NAME)
            return True
        except FileNotFoundError:
            return False

    # --- macOS Specific ---
    def _set_startup_macos(self, should_startup):
        plist_path = self._get_plist_path()
        if should_startup:
            plist_content = f"""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.unx-clipboard.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>{self.get_command()}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
            try:
                os.makedirs(os.path.dirname(plist_path), exist_ok=True)
                with open(plist_path, 'w') as f:
                    f.write(plist_content)
            except Exception as e:
                print(f"Error writing macOS plist file: {e}")
        else:
            if os.path.exists(plist_path):
                try:
                    os.remove(plist_path)
                except Exception as e:
                    print(f"Error removing macOS plist file: {e}")

    def _get_startup_macos(self):
        return os.path.exists(self._get_plist_path())

    # --- Linux Specific ---
    def _set_startup_linux(self, should_startup):
        desktop_file_path = self._get_linux_desktop_file_path()
        if should_startup:
            desktop_entry = f"""
[Desktop Entry]
Type=Application
Exec={self.get_command()}
Hidden=false
NoDisplay=false
Name=UNX Clipboard
Comment=Starts the UNX Clipboard manager
X-GNOME-Autostart-enabled=true
"""
            try:
                os.makedirs(os.path.dirname(desktop_file_path), exist_ok=True)
                with open(desktop_file_path, 'w') as f:
                    f.write(desktop_entry)
            except Exception as e:
                print(f"Error writing Linux .desktop file: {e}")
        else:
            if os.path.exists(desktop_file_path):
                try:
                    os.remove(desktop_file_path)
                except Exception as e:
                    print(f"Error removing Linux .desktop file: {e}")

    def _get_startup_linux(self):
        return os.path.exists(self._get_linux_desktop_file_path())

startup_manager = StartupManager()


class HotkeyListener:
    def __init__(self, hotkey_str, on_activate):
        self.hotkey_str = hotkey_str
        self.on_activate = on_activate
        self.listener = None
        self.thread = None

    def _run(self):
        try:
            self.listener = keyboard.GlobalHotKeys({self.hotkey_str: self.on_activate})
            self.listener.run()
        except Exception as e:
            print(f"Failed to start hotkey listener: {e}")

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self):
        if self.listener:
            self.listener.stop()


class SystemTrayIcon:
    def __init__(self, app_callbacks, image_object):
        self.icon = None
        self.app_callbacks = app_callbacks
        self.image_object = image_object

    def _create_menu(self):
        return Menu(
            MenuItem('Show/Hide Window', self.app_callbacks['toggle_window']),
            MenuItem('Settings...', lambda: self.app_callbacks['open_settings_requested'].emit()),
            Menu.SEPARATOR,
            MenuItem('Exit', self.app_callbacks['exit'])
        )

    def run(self):
        thread = Thread(target=self._run_icon, daemon=True)
        thread.start()

    def _run_icon(self):
        if not self.image_object:
            print("Cannot create tray icon: Image object is missing.")
            return
        try:
            self.icon = TrayIcon("UNXClipboard", self.image_object, "UNX Clipboard", self._create_menu())
            self.icon.run()
        except Exception as e:
            print(f"Failed to create tray icon: {e}")

    def stop(self):
        if self.icon:
            self.icon.stop()