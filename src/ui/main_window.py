import os
import sys
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QPushButton, QHBoxLayout
from PyQt5.QtCore import pyqtSignal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow

class MainWindow(BaseWindow):
    openSettings = pyqtSignal()
    startListening = pyqtSignal()
    closeApp = pyqtSignal()

    def __init__(self):
        """
        Initialize the main window.
        """
        super().__init__('WhisperWriter', 320, 180)
        self.initMainUI()

    def initMainUI(self):
        """
        Initialize the main user interface.
        """
        start_btn = QPushButton('Start')
        start_btn.setFont(QFont('Segoe UI', 10))
        start_btn.setFixedSize(120, 60)
        start_btn.clicked.connect(self.startPressed)

        settings_btn = QPushButton('Settings')
        settings_btn.setFont(QFont('Segoe UI', 10))
        settings_btn.setFixedSize(120, 60)
        settings_btn.clicked.connect(self.openSettings.emit)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(start_btn)
        button_layout.addWidget(settings_btn)
        button_layout.addStretch(1)

        self.main_layout.addStretch(1)
        self.main_layout.addLayout(button_layout)
        self.main_layout.addStretch(1)

    def closeEvent(self, event):
        """
        Close the application when the main window is closed.
        This happens when the user presses the close button or Alt+F4
        """
        self.closeApp.emit()

    def handleMinimizeButton(self):
        """
        Minimize the window to taskbar.
        """
        self.showMinimized()

    def handleCloseButton(self):
        """
        Hide the window to system tray.
        """
        self.hide()

    def startPressed(self):
        """
        Emit the startListening signal when the start button is pressed.
        """
        self.startListening.emit()
        self.hide()  # Hide the window, but keep the app running in the tray


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
