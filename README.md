-----

# UNX Clipboard

UNX Clipboard is a powerful, feature-rich, cross-platform clipboard manager built with Python and PyQt5. It extends your system's clipboard by providing a detailed history, advanced screenshot and editing tools, cloud-enabled backups, and other productivity features to streamline your workflow.

  \#\# ✨ Features

### Core Clipboard Functionality

  * **Complete History**: Saves a history of both text and images copied to the clipboard.
  * **Item Management**: Pin important items to the top and manage a dedicated list of reusable "Snippets".
  * **Instant Search**: Asynchronously search through your entire clipboard history without any delay.
  * **Pagination**: Easily browse through thousands of history items with a simple pagination system.
  * **Preview Pane**: View the full content of text entries and see clear previews of copied images.

### Advanced Screenshot Suite

  * **Multi-Mode Capture**:
      * **Region**: Click and drag to capture a specific area of your screen.
      * **Fullscreen**: Instantly capture your entire primary monitor.
      * **Active Window**: Capture only the currently focused application window.
  * **Integrated Image Editor**: An editor opens immediately after a screenshot is taken, equipped with:
      * **Drawing Tools**: Freehand pen and highlighter with a full-color picker.
      * **Shape Tools**: Draw rectangles to outline areas.
      * **Crop Tool**: Select and apply a crop to your screenshot.
      * **Undo/Redo**: Full support for all editing actions.

### Data & System Integration

  * **Total Backup & Restore**: A one-click feature to create a full backup (`.zip` file) of your entire database, images, and settings, and restore it seamlessly.
  * **Local Folder Sync**: A robust sync method that uses a local folder (managed by services like Google Drive Desktop, OneDrive, or Syncthing) to keep your application state synchronized across multiple computers.
  * **Backup Retention**: Automatically cleans up old backups, keeping your sync folder tidy based on your settings.
  * **Cross-Platform Startup**: A "Run on Startup" option in the settings.
  * **Global Hotkeys**: Configurable hotkeys to show/hide the app and launch the screenshot tool from anywhere.
  * **System Tray Icon**: For quick access to main functions and to run the app in the background.

### Productivity & Customization

  * **Discord Integration**: Automatically send your clipboard history to designated threads in a Discord server, creating a personal, searchable cloud archive.
  * **Theming**: Includes default Light and Dark themes, plus a full Custom Theme Editor to change all application colors and fonts.
  * **Password Generator**: A built-in tool to create strong, secure passwords.
  * **Surfing Tab**: A simple, integrated web browser for quick lookups.

-----

## 📂 Project Structure

The project is organized into several modules, each with a specific responsibility.

```
unx-clipboard/
│
├── config/
│   └── config.json           # Default config file (for packaging)
│
├── themes/
│   ├── dark_theme.qss        # Stylesheet for the dark theme
│   └── light_theme.qss       # Stylesheet for the light theme
│
├── clipboard_history.db      # Empty database file (for packaging)
├── config.py                 # Defines application paths and constants
├── core.py                   # Core logic: Database, ClipboardMonitor
├── create_build_files.py     # Helper script to prepare files for packaging
├── icon.ico                  # Application icon for Windows
├── icon.png                  # Application icon for Linux/macOS
├── main.py                   # Main application entry point and orchestrator
├── services.py               # High-level features: Sync, Import/Export, Discord
├── system.py                 # OS integration: Hotkeys, Tray Icon, Startup
├── ui.py                     # All GUI components (PyQt5)
└── UNX-Clipboard.spec        # PyInstaller specification file
```

### File Functions

  * **`main.py`**: The central hub that initializes all components, wires them together, and manages the application's lifecycle.
  * **`ui.py`**: Defines every visual element of the application using PyQt5, including the main window, all dialogs, and custom widgets.
  * **`core.py`**: Contains the application's "brain" and "memory," including the `Database` class and the `ClipboardMonitor`.
  * **`services.py`**: Implements high-level features like Import/Export, Cloud Sync, and Discord/Notion integrations.
  * **`system.py`**: Manages all interactions with the operating system, such as global hotkeys, the system tray icon, and startup management.
  * **`config.py`**: A simple module that defines the paths to user data directories and configuration files.
  * **`create_build_files.py`**: A utility script to ensure that the default database and configuration files are available before building the application.
  * **`UNX-Clipboard.spec`**: The configuration file for `PyInstaller`. This is the recommended way to build the application as it cleanly manages all data files and hidden imports.

-----

## 📦 Packaging for Production

To package this application, you must run the build process on the target operating system. You cannot cross-compile.

### Prerequisites

1.  **Install Python**: Ensure you have Python 3 installed.
2.  **Install Dependencies**: Navigate to the project's root directory and install all required packages.
    ```bash
    pip install -r requirements.txt
    ```
3.  **Prepare Build Files**: Run the helper script to create the necessary default files for packaging.
    ```bash
    python create_build_files.py
    ```

### 🖥️ Windows

Windows packaging is straightforward using the provided `.spec` file.

1.  **Run PyInstaller**: Open a terminal (Command Prompt or PowerShell), navigate to the project directory, and run:
    ```bash
    pyinstaller UNX-Clipboard.spec
    ```
2.  **Locate the Executable**: The final standalone application, `UNX-Clipboard.exe`, will be located in the `dist` folder.

### 🍎 macOS

Packaging for macOS creates a `.app` bundle. The process is similar, but you must specify a `.icns` file for the icon.

1.  **Create an `.icns` file**: macOS uses `.icns` for icons. You can convert the `icon.png` file using an online converter or a command-line tool.
2.  **Modify the `.spec` file**: Open `UNX-Clipboard.spec` and change the `icon` parameter in the `EXE` section to point to your new `.icns` file.
    ```python
    exe = EXE(
        ...
        icon='icon.icns' # Change from .ico to .icns
    )
    ```
3.  **Run PyInstaller**: From your terminal in the project directory, run:
    ```bash
    pyinstaller UNX-Clipboard.spec
    ```
4.  **Locate the App Bundle**: The final application, `UNX-Clipboard.app`, will be in the `dist` folder. You can drag this to your `Applications` folder.

### 🐧 Linux

Linux packaging creates a standalone executable file. The icon is not embedded directly but can be associated with the application via a `.desktop` file.

1.  **Run PyInstaller**: From your terminal in the project directory, run:
    ```bash
    pyinstaller UNX-Clipboard.spec
    ```
2.  **Locate the Executable**: The final executable, `UNX-Clipboard`, will be in the `dist` folder. You can run it directly from the terminal:
    ```bash
    ./dist/UNX-Clipboard
    ```
3.  **(Optional) Create a `.desktop` file**: To add the application to your desktop environment's menu, create a file named `unx-clipboard.desktop` in `~/.local/share/applications/` with the following content (adjust the paths as necessary):
    ```ini
    [Desktop Entry]
    Version=1.0
    Type=Application
    Name=UNX Clipboard
    Comment=A powerful, feature-rich clipboard manager.
    Exec=/path/to/your/dist/UNX-Clipboard
    Icon=/path/to/your/unx-clipboard/icon.png
    Terminal=false
    Categories=Utility;
    ```
