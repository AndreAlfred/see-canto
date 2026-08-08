import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from ui.tuner import TunerWidget


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_tuner_smoke(qt_app):
    w = TunerWidget()
    w.resize(240, 160)
    w.update_pitch(440.0)     # in tune
    w.grab()                  # forces paintEvent offscreen
    w.update_pitch(452.0)     # sharp
    w.grab()
    w.update_pitch(None)      # silence
    w.grab()
    w.set_theme_mode("dark")
    w.grab()
    w.set_theme_mode("light")
    w.grab()
