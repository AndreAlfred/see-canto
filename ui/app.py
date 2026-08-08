"""
ui/app.py — Main application window.

Loads AppSettings on startup, creates the spectrogram and pitch widgets,
wraps a SettingsPanel in a QDockWidget on the right, and wires everything
together so every settings change applies live and auto-saves to disk.
"""

import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QDockWidget, QToolBar,
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QAction

from audio.capture import AudioCapture
from audio.analysis import (
    MULTIRES_BANDS, MULTIRES_MAX_WINDOW,
    compute_multires_column, estimate_pitch, estimate_formants,
)
from ui import theme
from ui.ornaments import GildedFrame, attach_glow
from ui.settings import AppSettings
from ui.settings_panel import SettingsPanel
from ui.spectrogram import SpectrogramWidget
from ui.pitch_display import PitchDisplayWidget
from ui.tuner import TunerWidget

SAMPLE_RATE      = 44100
BLOCK_SIZE       = 1024
HOP_SIZE         = 1024   # analysis stride: ~43 columns/s scroll rate
PITCH_WINDOW     = 4096   # samples for pitch/formant estimation (~93 ms)
TIMER_INTERVAL_MS = 16


class MainWindow(QMainWindow):
    """Main application window for the voice trainer."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Trainer — Classical Singing Analysis")
        self.resize(1100, 650)

        self._settings = AppSettings.load()
        theme.set_mode(self._settings.theme_mode)

        self._capture = AudioCapture(sample_rate=SAMPLE_RATE, block_size=BLOCK_SIZE)
        self._audio_buffer = np.zeros(0, dtype=np.float32)
        # Rolling history sized for the longest multires band window; every
        # band's analysis window is a tail of this, ending at "now".
        self._history = np.zeros(MULTIRES_MAX_WINDOW, dtype=np.float32)

        self._setup_ui()
        self._setup_settings_dock()
        self._apply_theme_mode(self._settings.theme_mode)
        self._spectrogram.apply_settings(self._settings)

        self._capture.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._process_audio)
        self._timer.start(TIMER_INTERVAL_MS)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        self._central_layout = QVBoxLayout(central)

        # Title strip — marble lintel in light mode, flat band in dark
        # (styled per mode via #title_banner and _apply_theme_mode)
        self._title = QLabel()
        self._title.setObjectName("title_banner")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._central_layout.addWidget(self._title)

        # In light mode the spectrogram hangs in a gold-leaf picture frame;
        # in dark mode the frame collapses and it sits flush, as it used to
        self._spectrogram = SpectrogramWidget(
            sample_rate=SAMPLE_RATE,
            hop=HOP_SIZE,
            bands=MULTIRES_BANDS,
            display_seconds=self._settings.display_seconds,
        )
        self._frame = GildedFrame(self._spectrogram)
        self._central_layout.addWidget(self._frame, stretch=1)

        self._pitch_display = PitchDisplayWidget()
        self._central_layout.addWidget(self._pitch_display)

        self._tuner = TunerWidget()
        self._central_layout.addWidget(self._tuner)

    def _apply_theme_mode(self, mode: str) -> None:
        """Dress every mode-aware element for the given theme, live."""
        theme.set_mode(mode)
        self.setStyleSheet(theme.build_app_stylesheet(mode))

        if mode == "dark":
            self._central_layout.setContentsMargins(0, 0, 0, 0)
            self._central_layout.setSpacing(0)
            self._title.setText("VOICE TRAINER")
            self._title.setFont(QFont("Courier", 11))
            self._title.setFixedHeight(30)
        else:
            self._central_layout.setContentsMargins(14, 8, 14, 4)
            self._central_layout.setSpacing(6)
            self._title.setText(f"{theme.FLEURON}  · VOICE TRAINER ·  {theme.FLEURON}")
            self._title.setFont(QFont(theme.SERIF_FAMILY, 14, QFont.Weight.Bold))
            self._title.setFixedHeight(38)

        self._frame.set_ornate(mode != "dark")
        self._spectrogram.set_theme_mode(mode)
        self._pitch_display.set_theme_mode(mode)
        self._tuner.set_theme_mode(mode)
        self._settings_panel.set_theme_mode(mode)

    def _on_dark_mode_toggled(self, checked: bool) -> None:
        mode = "dark" if checked else "light"
        self._settings.theme_mode = mode
        self._settings.save()
        self._apply_theme_mode(mode)

    def _setup_settings_dock(self) -> None:
        self._settings_panel = SettingsPanel(self._settings)
        self._settings_panel.settings_changed.connect(self._on_settings_changed)

        dock = QDockWidget("Visual Settings", self)
        dock.setObjectName("settings_dock")
        dock.setWidget(self._settings_panel)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()
        self._settings_dock = dock

        toolbar = QToolBar("Settings", self)
        toolbar.setMovable(False)
        toggle = QAction("⚙  Settings", self)
        toggle.setCheckable(True)
        toggle.toggled.connect(dock.setVisible)
        dock.visibilityChanged.connect(toggle.setChecked)
        toolbar.addAction(toggle)

        dark_toggle = QAction("☾  Dark Mode", self)
        dark_toggle.setCheckable(True)
        dark_toggle.setChecked(self._settings.theme_mode == "dark")
        dark_toggle.toggled.connect(self._on_dark_mode_toggled)
        toolbar.addAction(dark_toggle)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        for action in (toggle, dark_toggle):
            btn = toolbar.widgetForAction(action)
            if btn is not None:
                attach_glow(btn)

    def _on_settings_changed(self, settings: AppSettings) -> None:
        # background_color applies to the spectrogram plot (inside
        # apply_settings); the window chrome keeps the theme stylesheet.
        self._spectrogram.apply_settings(settings)

    def _process_audio(self) -> None:
        new_chunks = []
        while True:
            chunk = self._capture.get_chunk()
            if chunk is None:
                break
            new_chunks.append(chunk)

        if not new_chunks:
            return

        self._audio_buffer = np.concatenate([self._audio_buffer] + new_chunks)
        latest_pitch = None

        while len(self._audio_buffer) >= HOP_SIZE:
            # Roll HOP_SIZE new samples into the fixed-length history; each
            # band then analyzes its own tail of the history, so all bands'
            # windows end at the same instant and the strips stay aligned.
            self._history = np.concatenate(
                [self._history[HOP_SIZE:], self._audio_buffer[:HOP_SIZE]])
            self._audio_buffer = self._audio_buffer[HOP_SIZE:]

            spectra = compute_multires_column(self._history, SAMPLE_RATE)
            recent = self._history[-PITCH_WINDOW:]
            pitch_hz     = estimate_pitch(recent, SAMPLE_RATE)
            f1_hz, f2_hz = estimate_formants(recent, SAMPLE_RATE)

            self._spectrogram.add_column(spectra)
            self._spectrogram.add_formants(f1_hz, f2_hz)

            if pitch_hz is not None:
                latest_pitch = pitch_hz

        self._pitch_display.update_pitch(latest_pitch)
        self._tuner.update_pitch(latest_pitch)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._capture.stop()
        event.accept()
