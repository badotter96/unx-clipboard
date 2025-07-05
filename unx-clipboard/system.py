import sys
import os
from threading import Thread
from pynput import keyboard
from PIL import Image
from pystray import Icon as TrayIcon, Menu, MenuItem

class StartupManager:
    APP_NAME = "UNX Clipboard"
    def get_executable_path(self):
        if getattr(sys, 'frozen', False): return sys.executable
        else: return sys.executable
        
    def set_startup_status(self, should_startup):
        if sys.platform == 'win32':
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.HKEY_CURRENT_USER
            try:
                with winreg.OpenKey(key, key_path, 0, winreg.KEY_ALL_ACCESS) as reg_key:
                    if should_startup:
                        exe_path = self.get_executable_path()
                        command = f'"{exe_path}"'
                        if not getattr(sys, 'frozen', False):
                            script_path = os.path.abspath(sys.argv[0])
                            command = f'"{exe_path}" "{script_path}"'
                        winreg.SetValueEx(reg_key, self.APP_NAME, 0, winreg.REG_SZ, command)
                    else:
                        winreg.DeleteValue(reg_key, self.APP_NAME)
            except FileNotFoundError:
                if should_startup:
                    try:
                        with winreg.CreateKey(key, key_path) as reg_key:
                            exe_path = self.get_executable_path()
                            command = f'"{exe_path}"'
                            if not getattr(sys, 'frozen', False):
                                script_path = os.path.abspath(sys.argv[0])
                                command = f'"{exe_path}" "{script_path}"'
                            winreg.SetValueEx(reg_key, self.APP_NAME, 0, winreg.REG_SZ, command)
                    except OSError as e: print(f"Error creating startup key: {e}")
            except Exception as e: print(f"Error accessing startup registry: {e}")

    def get_startup_status(self):
        if sys.platform == 'win32':
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                    winreg.QueryValueEx(key, self.APP_NAME)
                return True
            except FileNotFoundError:
                return False
        return False
startup_manager = StartupManager()


class HotkeyListener:
    def __init__(self, hotkey_str, on_activate):
        self.hotkey_str = hotkey_str; self.on_activate = on_activate
        self.listener = None; self.thread = None
    def _run(self):
        try:
            self.listener = keyboard.GlobalHotKeys({self.hotkey_str: self.on_activate})
            self.listener.run()
        except Exception as e:
            print(f"Failed to start hotkey listener: {e}")
    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = Thread(target=self._run, daemon=True); self.thread.start()
    def stop(self):
        if self.listener: self.listener.stop()

class SystemTrayIcon:
    def __init__(self, app_callbacks, image_object):
        self.icon = None; self.app_callbacks = app_callbacks
        self.image_object = image_object
    def _create_menu(self):
        return Menu(
            MenuItem('Show/Hide Window', self.app_callbacks['toggle_window']),
            MenuItem('Copy Last Text Item', self.app_callbacks['copy_last_item']),
            MenuItem('Settings...', lambda: self.app_callbacks['open_settings_requested'].emit()),
            Menu.SEPARATOR,
            MenuItem('Exit', self.app_callbacks['exit'])
        )
    def run(self):
        thread = Thread(target=self._run_icon, daemon=True); thread.start()
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
        if self.icon: self.icon.stop()