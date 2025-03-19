import os
import sys
import time
from audioplayer import AudioPlayer
from pynput.keyboard import Controller
from PyQt5.QtCore import QObject, QProcess, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox

from key_listener import KeyListener
from result_thread import ResultThread
from ui.settings_window import SettingsWindow
from ui.status_window import StatusWindow
from transcription import create_local_model
from input_simulation import InputSimulator
from utils import ConfigManager


class WhisperWriterApp(QObject):
    def __init__(self):
        """
        Initialize the application, opening settings window if no configuration file is found.
        """
        super().__init__()
        
        # Initialize the application
        self.app = QApplication(sys.argv)
        self.app.setWindowIcon(QIcon(os.path.join('assets', 'ww-logo.png')))
        
        # This is critical - prevent application from exiting when last window is closed
        self.app.setQuitOnLastWindowClosed(False)

        ConfigManager.initialize()

        # Create settings window
        self.settings_window = SettingsWindow()
        self.settings_window.settings_closed.connect(self.on_settings_closed)
        self.settings_window.settings_saved.connect(self.restart_app)
        
        # Create tray icon first so it's always available
        self.create_tray_icon()

        if ConfigManager.config_file_exists():
            self.initialize_components()
            self.start_listening()
        else:
            print('No valid configuration file found. Opening settings window...')
            self.settings_window.show()

    def initialize_components(self):
        """
        Initialize the components of the application.
        """
        self.input_simulator = InputSimulator()

        self.key_listener = KeyListener()
        self.key_listener.add_callback("on_activate", self.on_activation)
        self.key_listener.add_callback("on_deactivate", self.on_deactivation)

        model_options = ConfigManager.get_config_section('model_options')
        model_path = model_options.get('local', {}).get('model_path')
        self.local_model = create_local_model() if not model_options.get('use_api') else None

        self.result_thread = None

        if not ConfigManager.get_config_value('misc', 'hide_status_window'):
            self.status_window = StatusWindow()

    def create_tray_icon(self):
        """
        Create the system tray icon and its context menu.
        """
        # Create the tray icon
        self.tray_icon = QSystemTrayIcon(QIcon(os.path.join('assets', 'ww-logo.png')), self.app)
        
        # Create tray menu
        tray_menu = QMenu()

        # Add settings option
        settings_action = QAction('Settings', self.app)
        settings_action.triggered.connect(self.show_settings)
        tray_menu.addAction(settings_action)
        
        # Add separator
        tray_menu.addSeparator()

        # Add exit option
        exit_action = QAction('Exit', self.app)
        exit_action.triggered.connect(self.exit_app)
        tray_menu.addAction(exit_action)

        # Set the menu and make the icon visible
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Set tooltip
        self.tray_icon.setToolTip("WhisperWriter")
        
        # Optional: Add message to notify user the app is running in the system tray
        if not ConfigManager.config_file_exists():
            self.tray_icon.showMessage(
                "WhisperWriter",
                "Application is running in the system tray",
                QSystemTrayIcon.Information,
                3000
            )
    
    def show_settings(self):
        """
        Show the settings window and bring it to front.
        """
        # Ensure window is visible
        self.settings_window.show()
        
        # Bring window to front
        self.settings_window.setWindowState(
            self.settings_window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive
        )
        
        # These two calls help ensure the window comes to front on Windows
        self.settings_window.activateWindow()
        self.settings_window.raise_()

    def cleanup(self):
        """Clean up resources before exiting."""
        if hasattr(self, 'key_listener') and self.key_listener:
            self.key_listener.stop()
        if hasattr(self, 'input_simulator') and self.input_simulator:
            self.input_simulator.cleanup()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()

    def exit_app(self):
        """
        Exit the application.
        """
        self.cleanup()
        self.app.quit()

    def restart_app(self):
        """Restart the application to apply the new settings."""
        self.cleanup()
        self.app.quit()
        QProcess.startDetached(sys.executable, sys.argv)

    def on_settings_closed(self):
        """
        If settings is closed without saving on first run, initialize the components with default values.
        """
        if not os.path.exists(os.path.join('src', 'config.yaml')):
            QMessageBox.information(
                self.settings_window,
                'Using Default Values',
                'Settings closed without saving. Default values are being used.'
            )
            self.initialize_components()
            # Auto-start the app
            self.start_listening()

    def start_listening(self):
        """
        Start the key listener to listen for the activation key.
        """
        self.key_listener.start()
        # Show notification that app is now listening
        self.tray_icon.showMessage(
            "WhisperWriter Active", 
            "Listening for keyboard shortcut",
            QSystemTrayIcon.Information,
            2000
        )

    def on_activation(self):
        """
        Called when the activation key combination is pressed.
        """
        if self.result_thread and self.result_thread.isRunning():
            recording_mode = ConfigManager.get_config_value('recording_options', 'recording_mode')
            if recording_mode == 'press_to_toggle':
                self.result_thread.stop_recording()
            elif recording_mode == 'continuous':
                self.stop_result_thread()
            return

        self.start_result_thread()

    def on_deactivation(self):
        """
        Called when the activation key combination is released.
        """
        if ConfigManager.get_config_value('recording_options', 'recording_mode') == 'hold_to_record':
            if self.result_thread and self.result_thread.isRunning():
                self.result_thread.stop_recording()

    def start_result_thread(self):
        """
        Start the result thread to record audio and transcribe it.
        """
        if self.result_thread and self.result_thread.isRunning():
            return

        self.result_thread = ResultThread(self.local_model)
        if not ConfigManager.get_config_value('misc', 'hide_status_window'):
            self.result_thread.statusSignal.connect(self.status_window.updateStatus)
            self.status_window.closeSignal.connect(self.stop_result_thread)
        self.result_thread.resultSignal.connect(self.on_transcription_complete)
        self.result_thread.start()

    def stop_result_thread(self):
        """
        Stop the result thread.
        """
        if self.result_thread and self.result_thread.isRunning():
            self.result_thread.stop()

    def on_transcription_complete(self, result):
        """
        When the transcription is complete, type the result and start listening for the activation key again.
        """
        self.input_simulator.typewrite(result)

        if ConfigManager.get_config_value('misc', 'noise_on_completion'):
            AudioPlayer(os.path.join('assets', 'beep.wav')).play(block=True)

        if ConfigManager.get_config_value('recording_options', 'recording_mode') == 'continuous':
            self.start_result_thread()
        else:
            self.key_listener.start()

    def run(self):
        """
        Start the application.
        """
        sys.exit(self.app.exec_())


if __name__ == '__main__':
    app = WhisperWriterApp()
    app.run()
