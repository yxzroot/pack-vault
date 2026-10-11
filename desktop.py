#!/usr/bin/env python3
"""Pack Vault — a native resource-pack manager for Minecraft clients."""

import json
import getpass
from bisect import bisect_right
from time import monotonic
from datetime import datetime
import random
import re
import shutil
import sys
import math
from urllib.error import URLError
from pathlib import Path
import zipfile

from PySide6.QtCore import (Property, QEasingCurve, QParallelAnimationGroup, QPauseAnimation,
                             QPoint, QPropertyAnimation, QSequentialAnimationGroup, QSize, Qt, QTimer, QUrl,
                             QVariantAnimation, QThread, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QIcon, QKeySequence, QLinearGradient, QPainter,
                            QPainterPath, QPen, QPixmap, QRadialGradient, QShortcut)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QCheckBox,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QMenu, QSizePolicy, QStackedWidget, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from app import (DEFAULT_LIBRARY, DEFAULT_PACKS, app_directories, asset_path, discover_clients,
                  import_pack, install_from_library, list_packs, pack_data, toggle)
from features import (apply_profile, download_modrinth_pack, enabled_zip_names,
                      latest_modrinth_version, modrinth_slug, scan_conflicts)
from compatibility import FORMATS, convert_pack, detect_game_version, pack_format, pack_supports, texture_previews
from game_options import options_backups, read_order, restore_options_backup, write_order
from vault_tools import (duplicate_zips, export_profile, game_running, import_profile,
                          pack_backups, restore_pack_backup)
from lyrics import parse_lyrics
from now_playing import current_song, find_lyrics


SETTINGS = app_directories()[1] / "settings.json"
THEMES = {
    "Midnight": ("#0e101a", "#191d2c", "#333a52", "#b5a2ff", "#f7f5ff", "#a6abc1"),
    "Sakura": ("#211720", "#34232f", "#674159", "#f5a6c9", "#fff0f5", "#c8a6b8"),
    "Forest": ("#101c19", "#1c2d28", "#385a4e", "#9ce0b0", "#edf9f1", "#9dbbaa"),
    "Daylight": ("#f2eff9", "#ffffff", "#d7cce8", "#7752ad", "#271e33", "#71667e"),
    "Apple": ("#f5f5f7", "#ffffff", "#d2d2d7", "#007aff", "#1d1d1f", "#6e6e73"),
}


def stylesheet(theme):
    bg, surface, border, accent, text, muted = THEMES[theme]
    font = "'Inter', 'Noto Sans', 'Sans Serif'" if theme == "Apple" else "'Sans Serif'"
    rail = QColor(bg).lighter(108).name() if QColor(bg).lightness() < 140 else QColor(bg).darker(104).name()
    hover = QColor(surface).lighter(125).name() if QColor(bg).lightness() < 140 else QColor(surface).darker(106).name()
    return f"""
    QWidget {{ background: {bg}; color: {text}; font-family: {font}; font-size: 13px; }}
    QFrame#sidebar {{ background: {rail}; border-right: 1px solid {border}; }}
    QFrame#sidebar QLabel {{ background: transparent; }}
    QLabel#eyebrow, QLabel#count {{ color: {accent}; font-size: 11px; font-weight: 700; }}
    QLabel#title {{ font-size: 26px; font-weight: 800; }}
    QLabel#hello {{ font-size: 25px; font-weight: 800; }}
    QLabel#section {{ font-size: 21px; font-weight: 800; }}
    QLabel#dashboardHeading {{ font-size: 17px; font-weight: 800; }}
    QLabel#brand {{ font-size: 19px; font-weight: 800; }}
    QLabel#stat {{ font-size: 28px; font-weight: 800; color: {accent}; }}
    QLabel#sub, QLabel#path, QLabel#description, QLabel#hint, QLabel#muted {{ color: {muted}; }}
    QLabel#path {{ font-size: 11px; }}
    QLabel#pill {{ color: {accent}; background: {surface}; border: 1px solid {border};
                    border-radius: 14px; padding: 6px 12px; font-size: 11px; font-weight: 700; }}
    QFrame#card, QFrame#panel {{ background: {surface}; border: 1px solid {border}; border-radius: 17px; }}
    QFrame#dashboardRow {{ background: {surface}; border: 1px solid {border}; border-radius: 11px; }}
    QFrame#dashboardRow QLabel {{ background: transparent; }}
    QStackedWidget#lyricsDisplay, QWidget#lyricsCanvas, QWidget#lyricsCanvas QLabel {{ background: transparent; }}
    QFrame#card QLabel, QFrame#panel QLabel, QFrame#hero QLabel {{ background: transparent; }}
    QLabel#packname {{ font-size: 16px; font-weight: 700; }}
    QLabel#active {{ color: {accent}; font-size: 12px; font-weight: bold; }}
    QLabel#inactive {{ color: {muted}; font-size: 12px; font-weight: bold; }}
    QFrame#toast {{ background: {accent}; border-radius: 14px; }}
    QFrame#toast QLabel {{ color: {bg}; background: transparent; font-weight: bold; }}
    QLineEdit, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 11px;
                          padding: 8px 12px; min-height: 20px; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url("{asset_path('chevron.svg').as_posix()}"); width: 12px; height: 9px; }}
    QComboBox QAbstractItemView {{ background: {surface}; color: {text}; selection-background-color: {border};
                                   border: 1px solid {border}; padding: 6px; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
    QPushButton, QToolButton {{ background: {surface}; border: 1px solid {border}; border-radius: 11px;
                   padding: 8px 12px; font-weight: 700; min-height: 20px; }}
    QPushButton:hover, QToolButton:hover {{ background: {hover}; border-color: {accent}; }}
    QPushButton:focus, QToolButton:focus {{ border-color: {accent}; }}
    QPushButton:disabled {{ color: {muted}; }}
    QPushButton#primary {{ background: {accent}; color: {bg}; border-color: {accent}; }}
    QPushButton#primary:hover {{ background: {text}; border-color: {text}; }}
    QPushButton#nav {{ border: none; background: transparent; color: {muted}; text-align: left;
                       border-radius: 10px; padding: 10px 13px; font-size: 13px; }}
    QPushButton#nav:hover {{ color: {text}; background: {surface}; border: none; }}
    QPushButton#nav:checked {{ color: {accent}; background: {surface}; border: 1px solid {border}; }}
    QMenu {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 6px; }}
    QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {border}; color: {text}; }}
    QTabWidget::pane {{ border: none; }}
    QScrollArea, QListWidget {{ border: none; background: transparent; }}
    QListWidget::item {{ background: {surface}; border: 1px solid {border};
                         border-radius: 10px; margin: 3px; padding: 9px; }}
    QListWidget::item:selected {{ border-color: {accent}; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 0; }}
    QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 32px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 10px; padding: 8px; }}
    """


def navigation_icon(index, color):
    """Tiny vector icons avoid platform-dependent Unicode glyphs in the sidebar."""
    image = QPixmap(22, 22)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if index == 0:  # Home
        painter.drawLine(3, 10, 11, 3)
        painter.drawLine(11, 3, 19, 10)
        painter.drawRoundedRect(5, 9, 12, 10, 1, 1)
        painter.drawLine(9, 19, 9, 14)
        painter.drawLine(9, 14, 13, 14)
        painter.drawLine(13, 14, 13, 19)
    elif index == 1:  # Pack tiles
        for x in (4, 12):
            for y in (4, 12):
                painter.drawRoundedRect(x, y, 6, 6, 1, 1)
    elif index == 2:  # Library stack
        painter.drawRoundedRect(4, 3, 14, 5, 1, 1)
        painter.drawRoundedRect(4, 9, 14, 5, 1, 1)
        painter.drawRoundedRect(4, 15, 14, 5, 1, 1)
        painter.drawPoint(7, 5)
        painter.drawPoint(7, 11)
        painter.drawPoint(7, 17)
    elif index == 3:  # Loadouts
        for y in (5, 11, 17):
            painter.drawLine(4, y, 18, y)
        for x, y in ((10, 5), (15, 11), (8, 17)):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPoint(x, y), 2, 2)
    else:  # Ordering
        painter.drawLine(7, 4, 7, 18)
        painter.drawLine(4, 7, 7, 4)
        painter.drawLine(7, 4, 10, 7)
        painter.drawLine(4, 15, 7, 18)
        painter.drawLine(7, 18, 10, 15)
        painter.drawLine(13, 6, 18, 6)
        painter.drawLine(13, 11, 18, 11)
        painter.drawLine(13, 16, 18, 16)
    painter.end()
    return QIcon(image)


class AnimatedHero(QFrame):
    """A softly drifting, theme-aware glow behind the dashboard greeting."""

    def __init__(self):
        super().__init__()
        self.setObjectName("hero")
        self._phase = 0.0
        self.colors = THEMES["Midnight"]
        self.motion = QPropertyAnimation(self, b"phase", self)
        self.motion.setDuration(9000)
        self.motion.setStartValue(0.0)
        self.motion.setKeyValueAt(0.5, 1.0)
        self.motion.setEndValue(0.0)
        self.motion.setLoopCount(-1)
        self.motion.setEasingCurve(QEasingCurve.Type.InOutSine)

    def get_phase(self):
        return self._phase

    def set_phase(self, value):
        self._phase = value
        self.update()

    phase = Property(float, get_phase, set_phase)

    def set_theme(self, theme):
        self.colors = THEMES[theme]
        self.update()

    def set_motion(self, active):
        if active and self.motion.state() != self.motion.State.Running:
            self.motion.start()
        elif not active and self.motion.state() == self.motion.State.Running:
            self.motion.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(1, 1, -1, -1)
        bg, surface, _border, accent, _text, _muted = self.colors
        base = QLinearGradient(0, 0, self.width(), self.height())
        base.setColorAt(0, QColor(surface))
        base.setColorAt(1, QColor(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base)
        painter.drawRoundedRect(area, 26, 26)
        painter.setClipPath(self._rounded_path(area))
        color = QColor(accent)
        color.setAlpha(92)
        glow = QRadialGradient(self.width() * (0.7 + 0.15 * self._phase),
                               self.height() * (0.4 - 0.25 * self._phase), self.width() * 0.52)
        glow.setColorAt(0, color)
        color.setAlpha(0)
        glow.setColorAt(1, color)
        painter.fillRect(area, QBrush(glow))
        if self.width() > 680:
            decoration = QColor(accent)
            decoration.setAlpha(65)
            painter.setPen(QPen(decoration, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for offset in (0, 18, 36):
                painter.drawRoundedRect(self.width() - 166 + offset, 13 + offset // 2,
                                        80, 80, 17, 17)
            painter.setPen(Qt.PenStyle.NoPen)
            decoration.setAlpha(85)
            painter.setBrush(decoration)
            for x, y, size in ((self.width() - 176, 25, 5), (self.width() - 36, 29, 4),
                               (self.width() - 55, 91, 6)):
                painter.drawRect(x, y, size, size)
        painter.end()

    @staticmethod
    def _rounded_path(rect, radius=26):
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path


class AnimatedButton(QPushButton):
    """A visible, theme-aware ripple at the click position."""

    def __init__(self, *args):
        super().__init__(*args)
        self._ripple = 1.0
        self._hover = 0.0
        self._point = QPoint()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ripple_animation = QVariantAnimation(self)
        self.ripple_animation.setDuration(420)
        self.ripple_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ripple_animation.valueChanged.connect(self.set_ripple)
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(180)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.hover_animation.valueChanged.connect(self.set_hover)

    def set_ripple(self, value):
        self._ripple = float(value)
        self.update()

    def set_hover(self, value):
        self._hover = float(value)
        self.update()

    def enterEvent(self, event):
        self.animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animate_hover(0.0)
        super().leaveEvent(event)

    def animate_hover(self, target):
        self.hover_animation.stop()
        self.hover_animation.setStartValue(self._hover)
        self.hover_animation.setEndValue(target)
        self.hover_animation.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._point = event.position().toPoint()
            self.ripple_animation.stop()
            self.ripple_animation.setStartValue(0.0)
            self.ripple_animation.setEndValue(1.0)
            self.ripple_animation.start()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._ripple >= 1.0 and self._hover <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(AnimatedHero._rounded_path(self.rect(), 16))
        window = self.window()
        theme = window.theme_box.currentText() if hasattr(window, "theme_box") else "Midnight"
        color = QColor("#ffffff" if self.objectName() == "primary" else THEMES[theme][3])
        painter.setPen(Qt.PenStyle.NoPen)
        if self._hover > 0:
            color.setAlpha(int(28 * self._hover))
            painter.fillPath(AnimatedHero._rounded_path(self.rect(), 16), color)
        if self._ripple < 1.0:
            color.setAlpha(int(120 * (1 - self._ripple)))
            painter.setBrush(color)
            radius = math.hypot(self.width(), self.height()) * self._ripple
            painter.drawEllipse(self._point, int(radius), int(radius))
        painter.end()


class AnimatedCard(QFrame):
    """Pack card with a soft hover lift, without moving the surrounding layout."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self._hovered = False
        self.shadow_animation = None

    def enterEvent(self, event):
        self._hovered = True
        self.animate_shadow(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.animate_shadow(False)
        super().leaveEvent(event)

    def animate_shadow(self, highlighted):
        if isinstance(self.graphicsEffect(), QGraphicsOpacityEffect):
            return  # Wait until the card entrance finishes.
        shadow = self.graphicsEffect()
        if not isinstance(shadow, QGraphicsDropShadowEffect):
            if not highlighted:
                return
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(0)
            shadow.setOffset(0, 4)
            window = self.window()
            theme = window.theme_box.currentText() if hasattr(window, "theme_box") else "Midnight"
            color = QColor(THEMES[theme][3])
            color.setAlpha(115)
            shadow.setColor(color)
            self.setGraphicsEffect(shadow)
        if self.shadow_animation is not None:
            self.shadow_animation.stop()
        animation = QPropertyAnimation(shadow, b"blurRadius", self)
        animation.setStartValue(shadow.blurRadius())
        animation.setEndValue(28.0 if highlighted else 0.0)
        animation.setDuration(240)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        if not highlighted:
            animation.finished.connect(lambda: self.setGraphicsEffect(None) if not self._hovered else None)
        self.shadow_animation = animation
        animation.start()


class LyricsPlayer(QFrame):
    """Only lyric lines are visible; system media metadata stays off the dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.lines = []
        self.timestamps = []
        self.active_line = None
        self.lyric_animation = None
        self.track = None
        self.position = 0
        self.position_updated = monotonic()
        self.playing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        self.display = QStackedWidget()
        self.display.setObjectName("lyricsDisplay")
        self.display.setMinimumHeight(100)
        timed = QWidget()
        timed.setObjectName("lyricsCanvas")
        timed_layout = QVBoxLayout(timed)
        timed_layout.setContentsMargins(2, 0, 2, 0)
        timed_layout.setSpacing(2)
        self.current_lyric = QLabel("Play a song to see its lyrics.")
        self.current_lyric.setObjectName("dashboardHeading")
        self.current_lyric.setTextFormat(Qt.TextFormat.PlainText)
        self.current_lyric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_lyric.setWordWrap(True)
        timed_layout.addWidget(self.current_lyric, 1)
        self.next_lyric = QLabel(" ")
        self.next_lyric.setObjectName("sub")
        self.next_lyric.setTextFormat(Qt.TextFormat.PlainText)
        self.next_lyric.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_lyric.setWordWrap(True)
        timed_layout.addWidget(self.next_lyric, 1)
        self.display.addWidget(timed)
        self.plain_lyric = QLabel()
        self.plain_lyric.setObjectName("sub")
        self.plain_lyric.setTextFormat(Qt.TextFormat.PlainText)
        self.plain_lyric.setWordWrap(True)
        self.plain_lyric.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        sheet = QScrollArea()
        sheet.setWidgetResizable(True)
        sheet.setWidget(self.plain_lyric)
        self.display.addWidget(sheet)
        layout.addWidget(self.display)
        self.clock = QTimer(self)
        self.clock.setInterval(140)
        self.clock.timeout.connect(self.tick)
        self.clock.start()

    def show_song(self, song, lyric_text=None):
        if song is None:
            self.track = None
            self.lines = []
            self.active_line = None
            self.display.setCurrentIndex(0)
            self.current_lyric.setText("Play a song to see its lyrics.")
            self.next_lyric.setText(" ")
            return
        artist, title, duration, position, playing = song
        key = (artist, title, duration)
        if key != self.track:
            self.track = key
            self.set_lyrics("")
            self.current_lyric.setText("Finding lyrics…")
        self.position = position
        self.position_updated = monotonic()
        self.playing = playing
        if lyric_text is not None:
            self.set_lyrics(lyric_text)
            if not lyric_text:
                self.current_lyric.setText("Lyrics not available for this song.")
        self.tick()

    def set_lyrics(self, text):
        self.lines, plain = parse_lyrics(text)
        self.timestamps = [stamp for stamp, _ in self.lines]
        self.active_line = None
        if self.lines:
            self.display.setCurrentIndex(0)
            self.update_position(self.position)
        elif plain:
            self.plain_lyric.setText(plain)
            self.display.setCurrentIndex(1)
        else:
            self.display.setCurrentIndex(0)
            self.current_lyric.setText(" ")
            self.next_lyric.setText(" ")

    def tick(self):
        if self.track:
            elapsed = int((monotonic() - self.position_updated) * 1000) if self.playing else 0
            self.update_position(self.position + elapsed)

    def update_position(self, position):
        if not self.lines:
            return
        index = bisect_right(self.timestamps, position) - 1
        if index == self.active_line:
            return
        self.active_line = index
        self.current_lyric.setText(self.lines[index][1] if index >= 0 else " ")
        self.next_lyric.setText(self.lines[index + 1][1] if index + 1 < len(self.lines) else " ")
        if self.lyric_animation:
            self.lyric_animation.stop()
        effect = self.current_lyric.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.current_lyric)
            self.current_lyric.setGraphicsEffect(effect)
        self.lyric_animation = QPropertyAnimation(effect, b"opacity", self.current_lyric)
        self.lyric_animation.setStartValue(0.55)
        self.lyric_animation.setEndValue(1.0)
        self.lyric_animation.setDuration(220)
        self.lyric_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.lyric_animation.start()

class WelcomeTour(QDialog):
    STEPS = [
        ("✦", "Welcome to Pack Vault", "Keep your Minecraft texture packs together and use them across clients. Let's take a quick look around."),
        ("⌄", "Choose your client", "Open This client to pick a detected Minecraft client. Don't see yours? Use Add folder to choose its resourcepacks directory."),
        ("＋", "Import once, use anywhere", "Import ZIP saves a copy in My library and installs it in the selected client. On My library, press Install to add it to another client."),
        ("◈", "Make it yours", "Use Profiles to switch your ZIP sets, scan overlapping assets, and track Modrinth updates only if you opt in."),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Pack Vault")
        self.setModal(True)
        self.setFixedSize(475, 335)
        self.step = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 25)
        layout.setSpacing(14)
        self.progress = QLabel()
        self.progress.setObjectName("eyebrow")
        layout.addWidget(self.progress)
        self.symbol = QLabel()
        self.symbol.setObjectName("stat")
        layout.addWidget(self.symbol)
        self.heading = QLabel()
        self.heading.setObjectName("hello")
        layout.addWidget(self.heading)
        self.explanation = QLabel()
        self.explanation.setObjectName("sub")
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation, 1)
        controls = QHBoxLayout()
        self.skip = AnimatedButton("Skip tour")
        self.skip.clicked.connect(self.accept)
        controls.addWidget(self.skip)
        controls.addStretch()
        self.back = AnimatedButton("Back")
        self.back.clicked.connect(self.previous)
        controls.addWidget(self.back)
        self.next = AnimatedButton()
        self.next.setObjectName("primary")
        self.next.clicked.connect(self.advance)
        controls.addWidget(self.next)
        layout.addLayout(controls)
        self.step_animations = []
        self.show_step()

    def show_step(self):
        symbol, heading, explanation = self.STEPS[self.step]
        self.progress.setText(f"QUICK TOUR   ·   {self.step + 1} / {len(self.STEPS)}")
        self.symbol.setText(symbol)
        self.heading.setText(heading)
        self.explanation.setText(explanation)
        self.back.setEnabled(self.step > 0)
        self.next.setText("Let's go!" if self.step == len(self.STEPS) - 1 else "Next →")
        for animation in self.step_animations:
            animation.stop()
        self.step_animations.clear()
        for label in (self.symbol, self.heading, self.explanation):
            effect = label.graphicsEffect()
            if effect is None:
                effect = QGraphicsOpacityEffect(label)
                label.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            animation = QPropertyAnimation(effect, b"opacity", label)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setDuration(300)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.start()
            self.step_animations.append(animation)

    def previous(self):
        self.step -= 1
        self.show_step()

    def advance(self):
        if self.step == len(self.STEPS) - 1:
            self.accept()
        else:
            self.step += 1
            self.show_step()


class UpdateWorker(QThread):
    checked = Signal(object)

    def __init__(self, projects, library, game_version, parent=None):
        super().__init__(parent)
        self.projects = projects
        self.library = library
        self.game_version = game_version

    def run(self):
        versions, errors = {}, {}
        for name, slug in self.projects.items():
            if self.isInterruptionRequested():
                break
            try:
                versions[name] = latest_modrinth_version(
                    slug, installed_file=self.library / name, game_version=self.game_version)
            except (ValueError, OSError, URLError, KeyError, TypeError) as exc:
                errors[name] = str(exc)
        if not self.isInterruptionRequested():
            self.checked.emit((versions, errors))


class DownloadWorker(QThread):
    downloaded = Signal(object)
    failed = Signal(str)

    def __init__(self, file, version, library, parent=None):
        super().__init__(parent)
        self.file = file
        self.version = version
        self.library = library

    def run(self):
        try:
            path = download_modrinth_pack(self.file, self.library, self.version,
                                          cancelled=self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.downloaded.emit(path)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class DuplicateWorker(QThread):
    scanned = Signal(object)
    failed = Signal(str)

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.folders = folders

    def run(self):
        try:
            result = duplicate_zips(self.folders, cancelled=self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.scanned.emit(result)
        except OSError as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class NowPlayingWorker(QThread):
    updated = Signal(object, object)

    def run(self):
        previous = None
        retry_at = None
        while not self.isInterruptionRequested():
            song = current_song()
            key = song[:3] if song else None
            if key != previous:
                previous = key
                retry_at = None
                if not self.isInterruptionRequested():
                    self.updated.emit(song, None)
                if song:
                    try:
                        lyrics = find_lyrics(*song[:3])
                    except (OSError, ValueError, TypeError, KeyError):
                        lyrics = ""
                        retry_at = monotonic() + 30
                    if not self.isInterruptionRequested():
                        self.updated.emit(song, lyrics)
            elif song and not self.isInterruptionRequested():
                self.updated.emit(song, None)
                if retry_at is not None and monotonic() >= retry_at:
                    retry_at = monotonic() + 30
                    try:
                        lyrics = find_lyrics(*song[:3])
                    except (OSError, ValueError, TypeError, KeyError):
                        pass
                    else:
                        retry_at = None
                        if not self.isInterruptionRequested():
                            self.updated.emit(song, lyrics)
            for _ in range(20):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)


class AnimatedTabs(QTabWidget):
    """Keep the outgoing page visible while the next page comes into focus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlay = None
        self.overlay_animation = None

    def setCurrentIndex(self, index):
        if index == self.currentIndex() or not self.isVisible() or self.currentWidget() is None:
            super().setCurrentIndex(index)
            return
        if self.overlay_animation:
            self.overlay_animation.stop()
        if self.overlay:
            self.overlay.deleteLater()
            self.overlay = None
        old = self.currentWidget()
        snapshot = old.grab()
        rect = old.geometry()
        super().setCurrentIndex(index)
        if snapshot.isNull():
            return
        overlay = QLabel(self)
        overlay.setPixmap(snapshot)
        overlay.setGeometry(rect)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        overlay.show()
        overlay.raise_()
        animation = QPropertyAnimation(effect, b"opacity", overlay)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setDuration(210)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(overlay.deleteLater)
        animation.finished.connect(lambda: self.clear_overlay(overlay))
        self.overlay = overlay
        self.overlay_animation = animation
        animation.start()

    def clear_overlay(self, overlay):
        if self.overlay is overlay:
            self.overlay = None
            self.overlay_animation = None


class PackVault(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.settings = json.loads(SETTINGS.read_text())
            if not isinstance(self.settings, dict):
                self.settings = {}
        except (OSError, ValueError):
            self.settings = {}
        self.clients = []
        self.folder = DEFAULT_PACKS
        self.packs = []
        self.card_animations = []
        self.dashboard_animations = []
        self.number_animations = []
        self.stat_targets = [0, 0, 0]
        self._active_tab = 0
        self._page_animation = None
        self._heading_animation = None
        self._moving_page = None
        self._page_home = None
        self._toast = None
        self.toast_animation = None
        self.update_worker = None
        self.download_worker = None
        self.duplicate_worker = None
        self.now_playing_worker = None
        self.download_context = None
        self.update_mode = None
        self._waiting_to_close = False
        self.options_confirmed = False
        self.setAcceptDrops(True)
        self.setWindowTitle("Pack Vault · Minecraft resource packs")
        self.setWindowIcon(QIcon(str(asset_path("icon.svg"))))
        self.resize(1120, 760)
        self.setMinimumSize(650, 560)

        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(222)
        rail = QVBoxLayout(self.sidebar)
        rail.setContentsMargins(15, 21, 15, 17)
        rail.setSpacing(10)
        logo = QHBoxLayout()
        self.brand_icon = QLabel("✦")
        self.brand_icon.setObjectName("stat")
        self.brand_icon.setFixedWidth(32)
        logo.addWidget(self.brand_icon)
        self.brand_name = QLabel("Pack Vault")
        self.brand_name.setObjectName("brand")
        logo.addWidget(self.brand_name, 1)
        rail.addLayout(logo)
        self.rail_caption = QLabel("RESOURCE PACK STUDIO")
        self.rail_caption.setObjectName("eyebrow")
        rail.addWidget(self.rail_caption)
        rail.addSpacing(27)
        self.nav_heading = QLabel("WORKSPACE")
        self.nav_heading.setObjectName("hint")
        rail.addWidget(self.nav_heading)
        self.nav_buttons = []
        self.nav_shortcuts = []
        self.nav_items = ("Overview", "This client", "My library", "Profiles", "Pack order")
        for index, label in enumerate(self.nav_items):
            button = AnimatedButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolTip(f"{label}  ·  Ctrl+{index + 1}")
            button.setIconSize(QSize(18, 18))
            button.clicked.connect(lambda checked=False, i=index: self.tabs.setCurrentIndex(i))
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda i=index: self.tabs.setCurrentIndex(i))
            self.nav_shortcuts.append(shortcut)
            rail.addWidget(button)
            self.nav_buttons.append(button)
        rail.addStretch()
        self.rail_note = QLabel("One library. Every world.")
        self.rail_note.setObjectName("hint")
        self.rail_note.setWordWrap(True)
        rail.addWidget(self.rail_note)
        self.theme_caption = QLabel("APPEARANCE")
        self.theme_caption.setObjectName("eyebrow")
        rail.addWidget(self.theme_caption)
        self.theme_box = QComboBox()
        self.theme_box.addItems(THEMES)
        self.theme_box.setCurrentText(self.settings.get("theme", "Midnight") if
                                      self.settings.get("theme") in THEMES else "Midnight")
        self.theme_box.currentTextChanged.connect(self.change_theme)
        rail.addWidget(self.theme_box)
        self.theme_shortcut = AnimatedButton("Aa")
        self.theme_shortcut.setToolTip("Switch theme")
        self.theme_shortcut.clicked.connect(self.cycle_theme)
        self.theme_shortcut.hide()
        rail.addWidget(self.theme_shortcut)
        self.open_library_button = AnimatedButton("↗   Open library")
        self.open_library_button.clicked.connect(self.open_library)
        rail.addWidget(self.open_library_button)
        shell.addWidget(self.sidebar)

        main = QWidget()
        shell.addWidget(main, 1)
        layout = QVBoxLayout(main)
        layout.setContentsMargins(25, 19, 25, 16)
        layout.setSpacing(9)
        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        heading_text.setSpacing(2)
        self.breadcrumb = QLabel("PACK VAULT  /  OVERVIEW")
        self.breadcrumb.setObjectName("eyebrow")
        heading_text.addWidget(self.breadcrumb)
        self.page_title = QLabel("Welcome back")
        self.page_title.setObjectName("title")
        heading_text.addWidget(self.page_title)
        heading.addLayout(heading_text, 1)
        self.header_status = QLabel("●  Your collection")
        self.header_status.setObjectName("pill")
        heading.addWidget(self.header_status)
        layout.addLayout(heading)

        self.controls = QFrame()
        self.controls.setObjectName("panel")
        control_layout = QVBoxLayout(self.controls)
        control_layout.setContentsMargins(14, 10, 14, 9)
        control_layout.setSpacing(5)
        top = QHBoxLayout()
        client_field = QVBoxLayout()
        client_field.setSpacing(3)
        client_label = QLabel("MINECRAFT CLIENT")
        client_label.setObjectName("eyebrow")
        client_field.addWidget(client_label)
        self.client_box = QComboBox()
        self.client_box.setMinimumWidth(155)
        self.client_box.currentIndexChanged.connect(self.change_client)
        client_field.addWidget(self.client_box)
        top.addLayout(client_field, 1)
        version_field = QVBoxLayout()
        version_field.setSpacing(3)
        version_label = QLabel("GAME VERSION")
        version_label.setObjectName("eyebrow")
        version_field.addWidget(version_label)
        self.version_box = QComboBox()
        self.version_box.addItem("Choose version", "")
        for version in FORMATS:
            self.version_box.addItem(version, version)
        self.version_box.currentIndexChanged.connect(self.change_version)
        self.version_box.setMinimumWidth(120)
        version_field.addWidget(self.version_box)
        top.addLayout(version_field)
        add_client = AnimatedButton("＋")
        add_client.setToolTip("Add a Minecraft resourcepacks folder")
        add_client.setAccessibleName("Add client folder")
        add_client.clicked.connect(self.add_client)
        top.addWidget(add_client, alignment=Qt.AlignmentFlag.AlignBottom)
        refresh = AnimatedButton("↻")
        refresh.setToolTip("Find newly installed Minecraft clients")
        refresh.setAccessibleName("Refresh clients")
        refresh.clicked.connect(lambda: self.refresh_clients(manual=True))
        top.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignBottom)
        control_layout.addLayout(top)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("path")
        self.folder_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        control_layout.addWidget(self.folder_label)
        layout.addWidget(self.controls)

        self.toolbar = QWidget()
        toolbar = QHBoxLayout(self.toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕   Search your packs…")
        self.search.textChanged.connect(lambda _text: self.render())
        toolbar.addWidget(self.search, 1)
        self.tools_button = QToolButton()
        self.tools_button.setText("Tools  ▾")
        self.tools_button.setToolTip("Overlap scan, duplicates, updates and surprise")
        menu = QMenu(self.tools_button)
        menu.addAction("✦  Surprise me", self.pick_pack)
        menu.addSeparator()
        menu.addAction("◫  Scan overlaps", self.show_conflicts)
        menu.addAction("◈  Find duplicates", self.find_duplicates)
        menu.addAction("↻  Check updates", self.check_updates)
        self.tools_button.setMenu(menu)
        self.tools_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(self.tools_button)
        import_button = AnimatedButton("＋  Import ZIP")
        import_button.setObjectName("primary")
        import_button.clicked.connect(self.import_pack)
        toolbar.addWidget(import_button)
        layout.addWidget(self.toolbar)
        self.section = QWidget()
        section = QHBoxLayout(self.section)
        section.setContentsMargins(0, 5, 0, 0)
        self.section_label = QLabel("Your space")
        self.section_label.setObjectName("section")
        section.addWidget(self.section_label)
        section.addStretch()
        self.count = QLabel()
        self.count.setObjectName("count")
        section.addWidget(self.count)
        layout.addWidget(self.section)
        self.tabs = AnimatedTabs()
        self.tabs.tabBar().hide()
        self.cards = []
        dashboard = QWidget()
        overview = QVBoxLayout(dashboard)
        overview.setContentsMargins(4, 7, 9, 12)
        overview.setSpacing(12)
        self.hero = AnimatedHero()
        self.hero.setMinimumHeight(126)
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(26, 20, 26, 20)
        self.greeting = QLabel(f"Welcome back, {getpass.getuser()}")
        self.greeting.setObjectName("hello")
        hero_layout.addWidget(self.greeting)
        self.dashboard_client = QLabel()
        self.dashboard_client.setObjectName("sub")
        self.dashboard_client.setWordWrap(True)
        hero_layout.addWidget(self.dashboard_client)
        hero_layout.addStretch()
        overview.addWidget(self.hero)
        glance = QLabel("AT A GLANCE")
        glance.setObjectName("eyebrow")
        overview.addWidget(glance)
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_labels = []
        self.stat_tiles = []
        for caption in ("CLIENTS", "CLIENT PACKS", "LIBRARY PACKS"):
            tile = AnimatedCard()
            tile.setObjectName("panel")
            tile.setMinimumHeight(98)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(17, 12, 17, 12)
            value = QLabel("0")
            value.setObjectName("stat")
            tile_layout.addWidget(value)
            label = QLabel(caption)
            label.setObjectName("eyebrow")
            tile_layout.addWidget(label)
            stats.addWidget(tile, 1)
            self.stat_labels.append(value)
            self.stat_tiles.append(tile)
        overview.addLayout(stats)
        self.client_panel = AnimatedCard()
        self.client_panel.setObjectName("panel")
        client_layout = QHBoxLayout(self.client_panel)
        client_layout.setContentsMargins(18, 15, 18, 15)
        client_details = QVBoxLayout()
        client_details.setSpacing(3)
        client_caption = QLabel("CURRENT CLIENT")
        client_caption.setObjectName("eyebrow")
        client_details.addWidget(client_caption)
        self.dashboard_client_name = QLabel()
        self.dashboard_client_name.setObjectName("dashboardHeading")
        client_details.addWidget(self.dashboard_client_name)
        self.dashboard_version = QLabel()
        self.dashboard_version.setObjectName("sub")
        client_details.addWidget(self.dashboard_version)
        client_layout.addLayout(client_details, 1)
        manage_client = AnimatedButton("Manage packs →")
        manage_client.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        client_layout.addWidget(manage_client)
        overview.addWidget(self.client_panel)
        self.lyrics_player = LyricsPlayer(self)
        overview.addWidget(self.lyrics_player)
        self.recent_panel = AnimatedCard()
        self.recent_panel.setObjectName("panel")
        recent_layout = QVBoxLayout(self.recent_panel)
        recent_layout.setContentsMargins(18, 15, 18, 15)
        recent_layout.setSpacing(9)
        recent_header = QHBoxLayout()
        recent_title = QLabel("PACKS IN THIS CLIENT")
        recent_title.setObjectName("eyebrow")
        recent_header.addWidget(recent_title)
        recent_header.addStretch()
        browse = AnimatedButton("View all →")
        browse.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        recent_header.addWidget(browse)
        recent_layout.addLayout(recent_header)
        self.quick_packs = QVBoxLayout()
        self.quick_packs.setSpacing(6)
        recent_layout.addLayout(self.quick_packs)
        overview.addWidget(self.recent_panel)
        self.dashboard_sections = [self.hero, *self.stat_tiles, self.client_panel,
                                   self.lyrics_player, self.recent_panel]
        overview.addStretch()
        dashboard_scroll = QScrollArea()
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setWidget(dashboard)
        self.tabs.addTab(dashboard_scroll, "Dashboard")
        for label in ("This client", "My library"):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            cards = QVBoxLayout(container)
            cards.setAlignment(Qt.AlignmentFlag.AlignTop)
            cards.setSpacing(12)
            scroll.setWidget(container)
            self.tabs.addTab(scroll, label)
            self.cards.append(cards)
        profile_scroll = QScrollArea()
        profile_scroll.setWidgetResizable(True)
        profile_container = QWidget()
        self.profile_cards = QVBoxLayout(profile_container)
        self.profile_cards.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.profile_cards.setSpacing(12)
        profile_scroll.setWidget(profile_container)
        self.tabs.addTab(profile_scroll, "Profiles")
        order_page = QWidget()
        order_layout = QVBoxLayout(order_page)
        order_title = QLabel("Drag to set priority")
        order_title.setObjectName("section")
        order_layout.addWidget(order_title)
        order_hint = QLabel("Top = highest priority. Tick the packs you want Minecraft to select, then Save. Close Minecraft first; Pack Vault backs up options.txt before writing.")
        order_hint.setObjectName("sub")
        order_hint.setWordWrap(True)
        order_layout.addWidget(order_hint)
        self.order_list = QListWidget()
        self.order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        order_layout.addWidget(self.order_list, 1)
        self.order_state = QLabel()
        self.order_state.setObjectName("hint")
        self.order_state.setWordWrap(True)
        order_layout.addWidget(self.order_state)
        order_buttons = QHBoxLayout()
        refresh_order = AnimatedButton("↻  Reload")
        refresh_order.clicked.connect(self.render_order)
        order_buttons.addWidget(refresh_order)
        restore = AnimatedButton("Restore backup…")
        restore.clicked.connect(self.restore_options)
        order_buttons.addWidget(restore)
        restore_pack = AnimatedButton("Restore pack…")
        restore_pack.clicked.connect(self.restore_pack)
        order_buttons.addWidget(restore_pack)
        save_order = AnimatedButton("Save order to Minecraft")
        save_order.setObjectName("primary")
        save_order.clicked.connect(self.save_order)
        order_buttons.addWidget(save_order)
        order_buttons.addStretch()
        order_layout.addLayout(order_buttons)
        self.tabs.addTab(order_page, "Pack order")
        layout.addWidget(self.tabs, 1)
        self.footer_hint = QLabel("↘  Drop ZIPs anywhere to import  ·  originals stay safe in your library")
        self.footer_hint.setObjectName("hint")
        layout.addWidget(self.footer_hint)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.populate_clients()
        self.change_theme(self.theme_box.currentText())
        self.sync_navigation(self.tabs.currentIndex())
        self.update_responsive_layout()
        self.client_timer = QTimer(self)
        self.client_timer.setInterval(30000)
        self.client_timer.timeout.connect(self.refresh_clients)
        self.client_timer.start()
        if not self.settings.get("tour_complete"):
            QTimer.singleShot(0, self.show_tour)

    def show_tour(self):
        tour = WelcomeTour(self)
        if tour.exec() == QDialog.DialogCode.Accepted:
            self.settings["tour_complete"] = True
            self.save_settings()

    def save_settings(self):
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(self.settings, indent=2))

    def refresh_clients(self, manual=False):
        if not manual and not self.isVisible():
            return
        before = {self.client_box.itemData(i) for i in range(self.client_box.count())}
        discovered = {str(path) for _, path in discover_clients()}
        if discovered - before:
            self.populate_clients(self.folder)
            self.notify(f"Found {len(discovered - before)} new client(s)")
        elif manual:
            self.notify("Client list is up to date")

    def change_theme(self, theme):
        self.setStyleSheet(stylesheet(theme))
        self.hero.set_theme(theme)
        self.update_navigation_icons()
        self.settings["theme"] = theme
        self.save_settings()
        self.render()

    def cycle_theme(self):
        self.theme_box.setCurrentIndex((self.theme_box.currentIndex() + 1) % self.theme_box.count())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "nav_buttons") and hasattr(self, "folder_label"):
            self.update_responsive_layout()

    def update_responsive_layout(self):
        compact = self.width() < 900
        self.sidebar.setFixedWidth(64 if compact else 222)
        for button, label in zip(self.nav_buttons, self.nav_items):
            button.setText("" if compact else label)
            button.setAccessibleName(label)
        self.brand_name.setVisible(not compact)
        self.rail_caption.setVisible(not compact)
        self.nav_heading.setVisible(not compact)
        self.rail_note.setVisible(not compact)
        self.theme_caption.setVisible(not compact)
        self.theme_box.setVisible(not compact)
        self.theme_shortcut.setVisible(compact)
        self.open_library_button.setText("↗" if compact else "↗   Open library")
        self.open_library_button.setToolTip("Open library")
        self.open_library_button.setAccessibleName("Open library")
        self.header_status.setVisible(not compact)
        self.update_folder_label()

    def update_navigation_icons(self):
        colors = THEMES[self.theme_box.currentText()]
        for index, button in enumerate(self.nav_buttons):
            button.setIcon(navigation_icon(index, colors[3] if button.isChecked() else colors[5]))

    def update_folder_label(self):
        if not hasattr(self, "folder"):
            return
        text = f"RESOURCEPACKS  /  {self.folder}"
        self.folder_label.setToolTip(str(self.folder))
        width = max(140, self.folder_label.width() or self.width() - self.sidebar.width() - 70)
        self.folder_label.setText(self.folder_label.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideMiddle, width))

    def sync_navigation(self, index):
        if index < 0:
            return
        titles = ("Dashboard", "Client packs", "Your library", "Saved loadouts", "Pack priority")
        sections = ("", "Available in this client", "All your packs", "One-click loadouts", "Minecraft's order")
        self.page_title.setText(titles[index])
        self.section_label.setText(sections[index])
        self.breadcrumb.setText(f"PACK VAULT  /  {self.nav_items[index].upper()}")
        for widget in (self.controls, self.toolbar, self.section, self.footer_hint):
            widget.setVisible(index != 0)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        self.update_navigation_icons()

    def populate_clients(self, select=None):
        candidates = discover_clients()
        for entry in self.settings.get("custom_clients", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                continue
            path = Path(entry["path"]).expanduser()
            if (path.is_dir() or path.parent.is_dir()) and all(path != existing for _, existing in candidates):
                candidates.append((str(entry.get("name", path.parent.name)), path))
        # Keep the previously selected client available if it's OneClient and was not created yet.
        if not candidates:
            candidates = [("OneClient", DEFAULT_PACKS)]
        selected = str(select or self.settings.get("client", candidates[0][1]))
        self.client_box.blockSignals(True)
        self.client_box.clear()
        self.clients = candidates
        for name, folder in candidates:
            self.client_box.addItem(name, str(folder))
        index = self.client_box.findData(selected)
        self.client_box.setCurrentIndex(index if index >= 0 else 0)
        self.client_box.blockSignals(False)
        self.change_client()

    def change_client(self, _index=None):
        path = self.client_box.currentData()
        if not path:
            return
        self.folder = Path(path)
        self.options_confirmed = False
        self.update_folder_label()
        self.header_status.setText(f"●  {self.client_box.currentText()}")
        detected = detect_game_version(self.folder)
        selected = self.settings.get("client_versions", {}).get(path) or detected or ""
        self.version_box.blockSignals(True)
        index = self.version_box.findData(selected)
        self.version_box.setCurrentIndex(max(index, 0))
        self.version_box.blockSignals(False)
        self.settings["client"] = path
        self.save_settings()
        self.reload()

    def change_version(self):
        version = self.version_box.currentData() or ""
        self.settings.setdefault("client_versions", {})[str(self.folder)] = version
        self.save_settings()
        self.render()

    def selected_version(self):
        return self.version_box.currentData() or None

    def add_client(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose a client's resourcepacks folder", str(Path.home()))
        if not chosen:
            return
        folder = Path(chosen)
        if folder.name in (".minecraft", "minecraft"):
            folder = folder / "resourcepacks"
        if folder.name != "resourcepacks":
            answer = QMessageBox.question(self, "Use this folder?",
                "This folder isn't named 'resourcepacks'. Are you sure Minecraft uses it for texture packs?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        if folder.is_symlink() or folder.parent.is_symlink():
            self.error("Please select a real resourcepacks directory, not a symlink.")
            return
        if not any(folder == existing for _, existing in discover_clients()):
            custom = self.settings.setdefault("custom_clients", [])
            if not any(isinstance(c, dict) and c.get("path") == str(folder) for c in custom):
                custom.append({"name": folder.parent.name or "Custom client", "path": str(folder)})
        self.populate_clients(folder)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and all(url.isLocalFile() and url.toLocalFile().lower().endswith(".zip") for url in urls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self.import_files(files)
        event.acceptProposedAction()

    def import_files(self, files):
        imported, errors = [], []
        for source in files[:25]:
            try:
                if not source.is_file():
                    raise ValueError("Not a ZIP file")
                import_pack(source, self.folder, DEFAULT_LIBRARY)
                imported.append(source.name)
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                errors.append(f"{source.name}: {exc}")
        if imported:
            self.search.clear()
            self.reload()
            self.notify(f"Imported {len(imported)} pack(s) to {self.client_box.currentText()}")
        if errors:
            self.error("Could not import:\n" + "\n".join(errors[:5]))

    def reload(self):
        self.packs = list_packs(self.folder)
        self.render(animate=True)

    def on_tab_changed(self, index):
        self.sync_navigation(index)
        if self.isVisible():
            self.animate_heading()
        self.hero.set_motion(index == 0 and self.isVisible())
        self.render(animate=True)
        if index == 0 and self.isVisible():
            self.animate_dashboard()
        if self.isVisible():
            self.animate_tab(index)
        self._active_tab = index

    def animate_tab(self, index):
        if self._page_animation:
            self._page_animation.stop()
            self.finish_tab_animation()
        page = self.tabs.widget(index)
        if page is None:
            return
        origin = page.pos()
        direction = 1 if index > self._active_tab else -1
        start = origin + QPoint(direction * 26, 0)
        self._moving_page = page
        self._page_home = origin
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.92)
        page.setGraphicsEffect(effect)
        page.move(start)
        slide = QPropertyAnimation(page, b"pos", page)
        slide.setStartValue(start)
        slide.setEndValue(origin)
        slide.setDuration(620)
        slide.setEasingCurve(QEasingCurve.Type.InOutCubic)
        fade = QPropertyAnimation(effect, b"opacity", page)
        fade.setStartValue(0.92)
        fade.setEndValue(1.0)
        fade.setDuration(620)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation = QParallelAnimationGroup(page)
        animation.addAnimation(slide)
        animation.addAnimation(fade)
        animation.finished.connect(self.finish_tab_animation)
        self._page_animation = animation
        animation.start()

    def animate_heading(self):
        if self._heading_animation:
            self._heading_animation.stop()
        effect = self.page_title.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.page_title)
            self.page_title.setGraphicsEffect(effect)
        effect.setOpacity(0.55)
        fade = QPropertyAnimation(effect, b"opacity", self.page_title)
        fade.setStartValue(0.55)
        fade.setEndValue(1.0)
        fade.setDuration(540)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._heading_animation = fade
        fade.start()

    def finish_tab_animation(self):
        if self._moving_page is not None:
            self._moving_page.move(self._page_home)
            self._moving_page.setGraphicsEffect(None)
        self._moving_page = None
        self._page_home = None
        self._page_animation = None

    def showEvent(self, event):
        super().showEvent(event)
        self.hero.set_motion(self.tabs.currentIndex() == 0)
        if self.tabs.currentIndex() == 0:
            QTimer.singleShot(0, self.animate_dashboard)
        if QApplication.platformName() != "offscreen" and (self.now_playing_worker is None or
                                                              not self.now_playing_worker.isRunning()):
            self.now_playing_worker = NowPlayingWorker(self)
            self.now_playing_worker.updated.connect(self.lyrics_player.show_song)
            self.now_playing_worker.start()

    def hideEvent(self, event):
        self.hero.set_motion(False)
        super().hideEvent(event)

    def animate_stats(self, numbers):
        for animation in self.number_animations:
            animation.stop()
        self.number_animations.clear()
        for i, target in enumerate(numbers):
            old = self.stat_targets[i]
            if old == target:
                self.stat_labels[i].setText(str(target))
                continue
            animation = QVariantAnimation(self)
            animation.setStartValue(old)
            animation.setEndValue(target)
            animation.setDuration(800)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(lambda value, label=self.stat_labels[i]: label.setText(str(value)))
            animation.start()
            self.number_animations.append(animation)
        self.stat_targets = list(numbers)

    def animate_dashboard(self):
        for animation in self.dashboard_animations:
            animation.stop()
        self.dashboard_animations.clear()
        for index, widget in enumerate(self.dashboard_sections):
            effect = widget.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            fade = QPropertyAnimation(effect, b"opacity", widget)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setDuration(270)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            sequence = QSequentialAnimationGroup(widget)
            sequence.addAnimation(QPauseAnimation(index * 45, widget))
            sequence.addAnimation(fade)
            sequence.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
            self.dashboard_animations.append(sequence)
            sequence.start()

    def animate_cards(self, visible_cards):
        for animation in self.card_animations:
            animation.stop()
        self.card_animations.clear()
        for i, card in enumerate(visible_cards[:8]):
            effect = QGraphicsOpacityEffect(card)
            effect.setOpacity(0)
            card.setGraphicsEffect(effect)
            fade = QPropertyAnimation(effect, b"opacity", card)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setDuration(260)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            sequence = QSequentialAnimationGroup(card)
            sequence.addAnimation(QPauseAnimation(i * 35, card))
            sequence.addAnimation(fade)
            sequence.finished.connect(lambda c=card: self.finish_card_animation(c))
            sequence.start()
            self.card_animations.append(sequence)

    @staticmethod
    def finish_card_animation(card):
        card.setGraphicsEffect(None)
        if card._hovered:
            card.animate_shadow(True)

    def render(self, animate=False):
        if not self.cards:
            return
        tab = self.tabs.currentIndex()
        library = list_packs(DEFAULT_LIBRARY)
        self.count.setText(f"{len(self.packs)} in this client   ·   {len(library)} in your library")
        self.animate_stats((self.client_box.count(), len(self.packs), len(library)))
        self.dashboard_client.setText("Your resource packs, across every Minecraft client.")
        self.dashboard_client_name.setText(self.client_box.currentText())
        self.dashboard_version.setText(f"Minecraft {self.selected_version() or 'version not selected'}  ·  "
                                       f"{sum(bool(p['enabled']) for p in self.packs)} available pack(s)")
        while self.quick_packs.count():
            item = self.quick_packs.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for pack in self.packs[:3]:
            label = pack["name"].removesuffix(".disabled").removesuffix(".zip")
            row = QFrame()
            row.setObjectName("dashboardRow")
            line = QHBoxLayout(row)
            line.setContentsMargins(12, 5, 9, 5)
            line.setSpacing(8)
            icon = QLabel("✦")
            icon.setObjectName("active")
            line.addWidget(icon)
            title = QLabel(label)
            title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            title.setToolTip(pack["name"])
            line.addWidget(title, 1)
            state = QLabel("Available" if pack["enabled"] else "Hidden")
            state.setObjectName("active" if pack["enabled"] else "inactive")
            line.addWidget(state)
            button = AnimatedButton("Open →")
            button.setAccessibleName(f"Open {pack['name']}")
            button.clicked.connect(lambda checked=False, n=pack["name"]: self.open_quick_pack(n))
            line.addWidget(button)
            self.quick_packs.addWidget(row)
        if not self.packs:
            note = QLabel("No packs in this client yet. Open This client to import one.")
            note.setObjectName("hint")
            note.setWordWrap(True)
            self.quick_packs.addWidget(note)
        if tab == 0:
            return
        if tab == 3:
            self.render_profiles()
            return
        if tab == 4:
            self.render_order()
            return
        for animation in self.card_animations:
            animation.stop()
        self.card_animations.clear()
        cards = self.cards[tab - 1]
        while cards.count():
            item = cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        packs = self.packs if tab == 1 else library
        matches = [p for p in packs if self.search.text().casefold() in
                   (p["name"] + " " + p["description"]).casefold()]
        if not matches:
            empty = QLabel("No packs found. Click Import ZIP to add one, or try another search.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(170)
            cards.addWidget(empty)
        shown = []
        for pack in matches:
            card = self.card(pack, tab == 2)
            cards.addWidget(card)
            shown.append(card)
        if animate is True:
            self.animate_cards(shown)

    def open_quick_pack(self, name):
        self.tabs.setCurrentIndex(1)
        self.search.setText(name)

    def render_profiles(self):
        while self.profile_cards.count():
            item = self.profile_cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        path = str(self.folder)
        saved = self.settings.get("profiles", {}).get(path, {})
        active = self.settings.get("active_profiles", {}).get(path)
        header = QFrame()
        header.setObjectName("panel")
        layout = QVBoxLayout(header)
        title = QLabel("Your loadouts")
        title.setObjectName("hello")
        layout.addWidget(title)
        explanation = QLabel("Save the ZIPs currently available in this client. Activating a profile hides other ZIPs; deactivating restores the previous selection. Folder packs aren't changed.")
        explanation.setObjectName("sub")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        row = QHBoxLayout()
        save = AnimatedButton("＋  Save current as profile")
        save.setObjectName("primary")
        save.clicked.connect(self.save_profile)
        row.addWidget(save)
        import_button = AnimatedButton("Import profile…")
        import_button.clicked.connect(self.import_saved_profile)
        row.addWidget(import_button)
        if active:
            deactivate = AnimatedButton("Deactivate profile ↶")
            deactivate.clicked.connect(self.deactivate_profile)
            row.addWidget(deactivate)
        row.addStretch()
        layout.addLayout(row)
        self.profile_cards.addWidget(header)
        for name, entry in sorted(saved.items()):
            packs = entry.get("packs", []) if isinstance(entry, dict) else entry
            card = QFrame()
            card.setObjectName("card")
            line = QHBoxLayout(card)
            info = QVBoxLayout()
            label = QLabel(name + ("  ● ACTIVE" if active == name else ""))
            label.setObjectName("packname")
            info.addWidget(label)
            detail = QLabel(f"{len(packs)} ZIP pack(s) · " + (", ".join(packs[:3]) or "Empty loadout"))
            detail.setObjectName("description")
            detail.setWordWrap(True)
            info.addWidget(detail)
            line.addLayout(info, 1)
            if name != active:
                activate = AnimatedButton("Activate")
                activate.setObjectName("primary")
                activate.clicked.connect(lambda checked=False, n=name: self.activate_profile(n))
                line.addWidget(activate)
            export_button = AnimatedButton("Export")
            export_button.clicked.connect(lambda checked=False, n=name: self.export_saved_profile(n))
            line.addWidget(export_button)
            remove = AnimatedButton("Remove")
            remove.clicked.connect(lambda checked=False, n=name: self.remove_profile(n))
            line.addWidget(remove)
            self.profile_cards.addWidget(card)

    def render_order(self):
        self.order_list.clear()
        available = [p["name"] for p in self.packs if p["enabled"]]
        try:
            selected = read_order(self.folder)
            self.order_state.setText("Minecraft's current selection loaded. Drag a pack to change priority.")
        except (OSError, ValueError, UnicodeError) as exc:
            selected = []
            self.order_state.setText(str(exc))
        top_first = [name for name in reversed(selected) if name in available]
        top_first += [name for name in available if name not in top_first]
        for name in top_first:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(Qt.CheckState.Checked if name in selected else Qt.CheckState.Unchecked)
            self.order_list.addItem(item)

    def confirm_options_write(self):
        if game_running(self.folder):
            self.error("Minecraft is running in this client. Close it before changing packs or options.txt.")
            return False
        if self.options_confirmed:
            return True
        answer = QMessageBox.question(self, "Close Minecraft first",
            "Changing selected packs while Minecraft is open can be overwritten by the game. "
            "Have you closed this client? Pack Vault will back up options.txt before writing.")
        if answer == QMessageBox.StandardButton.Yes:
            self.options_confirmed = True
            return True
        return False

    def save_order(self):
        try:
            read_order(self.folder)
            if not self.confirm_options_write():
                return
            top_first = [self.order_list.item(i).data(Qt.ItemDataRole.UserRole)
                         for i in range(self.order_list.count())
                         if self.order_list.item(i).checkState() == Qt.CheckState.Checked]
            backup = write_order(self.folder, list(reversed(top_first)))
            self.notify("Pack order saved" + (f" · backup: {backup.name}" if backup else " · no changes"))
        except (OSError, ValueError, UnicodeError) as exc:
            self.error(exc)

    def restore_options(self):
        backups = options_backups(self.folder)
        if not backups:
            return self.notify("No Pack Vault options backups for this client yet")
        labels = [f"{path.stem.removeprefix('options-')} · {path.stat().st_size:,} bytes"
                  for path in backups]
        label, ok = QInputDialog.getItem(self, "Restore pack order backup",
            "Choose a snapshot of options.txt. Current settings will be backed up first:", labels, 0, False)
        if not ok:
            return
        backup = backups[labels.index(label)]
        if not self.confirm_options_write():
            return
        if QMessageBox.question(self, "Restore Minecraft settings?",
                f"Restore {backup.name}? This restores ALL options in that snapshot, not only pack order. "
                "Your current options.txt will be backed up first.") != QMessageBox.StandardButton.Yes:
            return
        try:
            undo = restore_options_backup(self.folder, backup)
            self.render_order()
            self.notify(f"Restored options · undo backup: {undo.name}" if undo else "Already using this backup")
        except (OSError, ValueError, UnicodeError) as exc:
            self.error(exc)

    def restore_pack(self):
        backups = pack_backups(self.folder)
        if not backups:
            return self.notify("No pack backups for this client yet")
        labels = [f"{path.name}  ·  {'folder' if path.is_dir() else 'ZIP'}" for path in backups]
        label, ok = QInputDialog.getItem(self, "Restore a saved pack",
            "Restore a backup as a NEW pack without overwriting the original:", labels, 0, False)
        if not ok:
            return
        try:
            restored = restore_pack_backup(self.folder, backups[labels.index(label)])
            self.reload()
            self.notify(f"Restored {restored.name} · select it in Pack order when ready")
        except (OSError, ValueError) as exc:
            self.error(exc)

    def save_profile(self):
        name, ok = QInputDialog.getText(self, "Save profile", "Profile name (e.g. PvP or Skyblock):")
        name = name.strip()
        if not ok or not name:
            return
        if len(name) > 48:
            return self.error("Profile names must be under 49 characters")
        profiles = self.settings.setdefault("profiles", {}).setdefault(str(self.folder), {})
        if name in profiles and QMessageBox.question(self, "Replace profile?",
                f"Replace your saved '{name}' profile with the current available ZIPs?") != QMessageBox.StandardButton.Yes:
            return
        try:
            order = read_order(self.folder)
        except (OSError, ValueError, UnicodeError):
            order = None
        available = enabled_zip_names(self.folder)
        if order is not None:
            # Keep selected folder packs, but never save an unavailable ZIP into a loadout.
            order = [item for item in order if item in available or (self.folder / item).is_dir()]
        profiles[name] = {"packs": available, "order": order}
        self.save_settings()
        self.render_profiles()
        self.notify(f"Saved profile {name}")

    def export_saved_profile(self, name):
        entry = self.settings.get("profiles", {}).get(str(self.folder), {}).get(name)
        if entry is None:
            return self.error("Profile not found")
        chosen, _ = QFileDialog.getSaveFileName(self, "Export profile", str(Path.home() / f"{name}.json"),
                                                 "Pack Vault profiles (*.json)")
        if not chosen:
            return
        try:
            export_profile(Path(chosen), name, entry, self.selected_version())
            self.notify("Profile exported · ZIPs are not included")
        except FileExistsError:
            self.error("Export already exists. Choose another filename; no files were overwritten.")
        except (OSError, ValueError) as exc:
            self.error(exc)

    def import_saved_profile(self):
        chosen, _ = QFileDialog.getOpenFileName(self, "Import profile", str(Path.home()),
                                                "Pack Vault profiles (*.json)")
        if not chosen:
            return
        try:
            name, entry = import_profile(Path(chosen))
            profiles = self.settings.setdefault("profiles", {}).setdefault(str(self.folder), {})
            if name in profiles:
                alternate, ok = QInputDialog.getText(self, "Profile already exists",
                    "Choose a different name for the imported profile (existing loadout won't change):",
                    text=f"{name[:36]} (imported)")
                if not ok:
                    return
                name = alternate.strip()
                if not name or len(name) > 48 or name in profiles:
                    raise ValueError("Choose a unique profile name of at most 48 characters")
            profiles[name] = entry
            self.save_settings()
            self.render_profiles()
            self.notify("Profile imported · install its ZIPs into your library before activating")
        except (OSError, ValueError, UnicodeError) as exc:
            self.error(exc)

    def activate_profile(self, name):
        path = str(self.folder)
        entry = self.settings.get("profiles", {}).get(path, {}).get(name)
        if entry is None:
            return self.error("Profile not found")
        wanted = entry.get("packs", []) if isinstance(entry, dict) else entry
        order = entry.get("order") if isinstance(entry, dict) else None
        current = self.settings.get("active_profiles", {}).get(path)
        previous = self.settings.get("profile_previous", {}).get(path)
        before = enabled_zip_names(self.folder)
        if game_running(self.folder):
            return self.error("Minecraft is running in this client. Close it before activating a profile.")
        try:
            old_order = read_order(self.folder) if order is not None else None
        except (OSError, ValueError, UnicodeError) as exc:
            return self.error(exc)
        if order is not None and not self.confirm_options_write():
            return
        try:
            apply_profile(self.folder, wanted, DEFAULT_LIBRARY)
            if order is not None:
                write_order(self.folder, order, allow_hidden=True)
        except (ValueError, OSError) as exc:
            try:
                apply_profile(self.folder, before, DEFAULT_LIBRARY)
            except (OSError, ValueError):
                pass  # Report the original failure; existing options backups remain available.
            return self.error(exc)
        if not current or previous is None:
            self.settings.setdefault("profile_previous", {})[path] = before
            if old_order is not None:
                self.settings.setdefault("profile_previous_order", {})[path] = old_order
        self.settings.setdefault("active_profiles", {})[path] = name
        self.save_settings()
        self.reload()
        self.notify(f"Activated {name}")

    def deactivate_profile(self):
        path = str(self.folder)
        previous = self.settings.get("profile_previous", {}).get(path)
        if previous is None:
            return self.error("No previous pack selection was saved")
        if game_running(self.folder):
            return self.error("Minecraft is running in this client. Close it before deactivating a profile.")
        old_order = self.settings.get("profile_previous_order", {}).get(path)
        if old_order is not None and not self.confirm_options_write():
            return
        current = enabled_zip_names(self.folder)
        try:
            apply_profile(self.folder, previous, DEFAULT_LIBRARY)
            if old_order is not None:
                write_order(self.folder, old_order, allow_hidden=True)
        except (OSError, ValueError) as exc:
            try:
                apply_profile(self.folder, current, DEFAULT_LIBRARY)
            except (OSError, ValueError):
                pass
            return self.error(exc)
        self.settings.get("active_profiles", {}).pop(path, None)
        self.settings.get("profile_previous", {}).pop(path, None)
        self.settings.get("profile_previous_order", {}).pop(path, None)
        self.save_settings()
        self.reload()
        self.notify("Previous pack selection restored")

    def remove_profile(self, name):
        path = str(self.folder)
        if self.settings.get("active_profiles", {}).get(path) == name:
            return self.error("Deactivate this profile before removing it")
        if QMessageBox.question(self, "Remove profile?", f"Remove saved profile '{name}'? Packs won't be deleted.") != QMessageBox.StandardButton.Yes:
            return
        self.settings.get("profiles", {}).get(path, {}).pop(name, None)
        self.save_settings()
        self.render_profiles()

    def show_conflicts(self):
        conflicts = scan_conflicts(self.folder)
        if not conflicts:
            return self.notify("No overlapping assets found in available ZIPs")
        lines = [f"{path}\n    {' + '.join(packs)}" for path, packs in conflicts[:12]]
        QMessageBox.information(self, "Overlapping pack assets",
            "These ZIPs contain the same asset paths. Overlays can be intentional; change pack order in Minecraft if a texture looks wrong.\n\n"
            + "\n\n".join(lines) + ("\n\n…more overlaps not shown" if len(conflicts) > 12 else ""))

    def find_duplicates(self):
        if self.duplicate_worker is not None:
            return self.notify("Already scanning duplicates…")
        worker = DuplicateWorker((DEFAULT_LIBRARY, self.folder), self)
        self.duplicate_worker = worker
        worker.scanned.connect(self.show_duplicates)
        worker.failed.connect(self.error)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "duplicate_worker", None))
        worker.start()
        self.notify("Scanning ZIP hashes · originals won't be changed…")

    def show_duplicates(self, groups):
        if not groups:
            return self.notify("No duplicate ZIP contents found")
        lines = [" = ".join(str(path) for path in group) for group in groups[:15]]
        QMessageBox.information(self, "Duplicate pack contents",
            f"Found {len(groups)} group(s) with identical bytes. Library symlinks to the same file are ignored. "
            "No files were changed.\n\n" + "\n\n".join(lines) +
            ("\n\n…more groups not shown" if len(groups) > 15 else ""))

    def track_updates(self, name):
        tracked = self.settings.get("tracked_updates", {}).get(name, {})
        slug, ok = QInputDialog.getText(self, "Track Modrinth updates",
            "Modrinth resource-pack link or project slug (only checked when you click Check updates):",
            text=tracked.get("slug", ""))
        if not ok:
            return
        try:
            slug = modrinth_slug(slug)
        except ValueError as exc:
            return self.error(exc)
        self.start_update_check({name: slug}, baseline=True)

    def stop_tracking(self, name):
        self.settings.get("tracked_updates", {}).pop(name, None)
        self.save_settings()
        self.render()
        self.notify(f"Stopped tracking {name}")

    def check_updates(self):
        tracked = self.settings.get("tracked_updates", {})
        if not tracked:
            return self.notify("Track a library pack first to check updates")
        if len(tracked) > 10:
            self.notify("Checking the first 10 tracked packs (limit per check)")
        projects = {name: info["slug"] for name, info in list(tracked.items())[:10]
                    if (DEFAULT_LIBRARY / name).is_file()}
        if not projects:
            return self.notify("No tracked library packs were found")
        self.start_update_check(projects, baseline=False)

    def start_update_check(self, projects, baseline):
        if self.update_worker is not None:
            return self.notify("An update check is already running")
        self.update_mode = (baseline, projects)
        worker = UpdateWorker(projects, DEFAULT_LIBRARY, self.selected_version(), self)
        self.update_worker = worker
        worker.checked.connect(self.handle_update_results)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "update_worker", None))
        worker.start()
        self.notify("Checking Modrinth…")

    def handle_update_results(self, outcome):
        versions, errors = outcome
        baseline, projects = self.update_mode
        if baseline:
            for name, version in versions.items():
                installed_id = version.get("installed_id")
                compatible = version.get("compatible") or {}
                self.settings.setdefault("tracked_updates", {})[name] = {
                    "slug": projects[name], "id": installed_id or version["id"],
                    "compatible_id": installed_id or compatible.get("id")}
            if versions:
                self.save_settings()
                matched = next(iter(versions.values())).get("installed_id")
                self.notify("Pack version identified by hash" if matched else
                            "Tracking enabled · ZIP version unknown; latest release is baseline")
                self.render()
        else:
            updated = [f"{name}: {version['number']}\n{version['url']}" for name, version in versions.items()
                       if version["id"] != self.settings.get("tracked_updates", {}).get(name, {}).get("id")]
            if updated:
                QMessageBox.information(self, "Updates available", "New Modrinth versions:\n\n" + "\n\n".join(updated))
            elif not errors:
                self.notify("No new releases since tracking began")
            compatible_updates = [(name, version["compatible"]) for name, version in versions.items()
                if version.get("compatible") and version["compatible"]["id"] !=
                self.settings.get("tracked_updates", {}).get(name, {}).get("compatible_id")]
            if compatible_updates:
                choices = [f"{name} → {info['number']}" for name, info in compatible_updates]
                choice, ok = QInputDialog.getItem(self, "Compatible update found",
                    f"New release for Minecraft {self.selected_version()}. Choose a pack to download (original kept):",
                    choices, 0, False)
                if ok:
                    name, info = compatible_updates[choices.index(choice)]
                    self.download_update(name, info)
        if errors:
            QMessageBox.warning(self, "Update check", "Could not check:\n" + "\n".join(f"{n}: {e}" for n, e in errors.items()))

    def download_update(self, old_name, info):
        if self.download_worker is not None:
            return self.notify("A download is already running")
        self.download_context = (old_name, info, self.folder)
        worker = DownloadWorker(info["file"], info["number"], DEFAULT_LIBRARY, self)
        self.download_worker = worker
        worker.downloaded.connect(self.finish_download)
        worker.failed.connect(self.error)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "download_worker", None))
        worker.start()
        self.notify("Downloading and verifying update…")

    def finish_download(self, destination):
        old_name, info, client_folder = self.download_context
        self.reload()
        if self.folder != client_folder:
            return self.notify(f"Update saved in library: {destination.name}. Select the original client to install it.")
        answer = QMessageBox.question(self, "Verified update saved",
            f"Saved {destination.name} in your library with its SHA-512 hash verified. "
            "Install it into this client? The original pack stays untouched for rollback.")
        if answer != QMessageBox.StandardButton.Yes:
            return self.notify(f"Update saved in library: {destination.name}")
        try:
            install_from_library(destination.name, self.folder, DEFAULT_LIBRARY)
            try:
                order = read_order(self.folder)
            except (OSError, ValueError, UnicodeError):
                order = []
            if old_name in order and not self.confirm_options_write():
                self.reload()
                return self.notify(f"Installed {destination.name}; selection unchanged. Select it in Pack order when ready.")
            if old_name in order:
                old = self.folder / old_name
                backups = self.folder.parent / "pack-vault-backups"
                backups.mkdir(exist_ok=True)
                backup = backups / f"{old_name}.before-{info['id']}.zip"
                if not backup.exists() and old.is_file():
                    shutil.copy2(old, backup)
                write_order(self.folder, [destination.name if name == old_name else name for name in order])
            self.settings.setdefault("update_rollback", {})[destination.name] = old_name
            self.settings.setdefault("tracked_updates", {})[destination.name] = {
                "slug": self.settings.get("tracked_updates", {}).get(old_name, {}).get("slug"),
                "id": info["id"], "compatible_id": info["id"]}
            self.save_settings()
            self.reload()
            self.notify(f"Installed {destination.name}. Original kept for rollback.")
        except (OSError, ValueError) as exc:
            self.error(f"Update saved in library, but could not fully activate: {exc}")

    def rollback_update(self, new_name):
        old_name = self.settings.get("update_rollback", {}).get(new_name)
        if not old_name:
            return self.error("No previous pack recorded for this update")
        try:
            order = read_order(self.folder)
            if new_name not in order:
                return self.notify("Updated pack is not selected here. Select the original in Pack order.")
            if not self.confirm_options_write():
                return
            if not (self.folder / old_name).is_file():
                if (self.folder / (old_name + ".disabled")).is_file():
                    toggle(self.folder, old_name + ".disabled")
                elif (DEFAULT_LIBRARY / old_name).is_file():
                    install_from_library(old_name, self.folder, DEFAULT_LIBRARY)
                else:
                    raise ValueError(f"Original pack not found: {old_name}")
            write_order(self.folder, [old_name if name == new_name else name for name in order])
            self.notify(f"Restored {old_name} as the selected pack. Updated ZIP kept.")
            self.reload()
        except (OSError, ValueError) as exc:
            self.error(exc)

    def closeEvent(self, event):
        running = [worker for worker in (self.update_worker, self.download_worker, self.duplicate_worker,
                                         self.now_playing_worker)
                    if worker is not None and worker.isRunning()]
        if running:
            for worker in running:
                worker.requestInterruption()
                if not self._waiting_to_close:
                    worker.finished.connect(self.close)
            self._waiting_to_close = True
            event.ignore()  # Never destroy a QThread while a network request is in flight.
            self.notify("Finishing the current network request before closing…")
            return
        super().closeEvent(event)

    def card(self, pack, from_library):
        card = AnimatedCard()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 13, 16, 12)
        outer.setSpacing(9)
        row = QHBoxLayout()
        row.setSpacing(13)
        icon = QLabel("✦")
        icon.setFixedSize(54, 54)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        palette = THEMES[self.theme_box.currentText()]
        icon.setStyleSheet(f"font-size: 24px; color: {palette[3]}; background: {palette[2]}; border-radius: 12px")
        if pack["icon"]:
            image = pack_data((DEFAULT_LIBRARY if from_library else self.folder) / pack["name"])[1]
            pixmap = QPixmap()
            if image and pixmap.loadFromData(image, "PNG"):
                icon.setPixmap(pixmap.scaled(54, 54, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.FastTransformation))
        row.addWidget(icon)
        info = QVBoxLayout()
        info.setSpacing(2)
        display_name = pack["name"].removesuffix(".disabled").removesuffix(".zip")
        name = QLabel(display_name[:65] + ("…" if len(display_name) > 65 else ""))
        name.setObjectName("packname")
        name.setToolTip(pack["name"])
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(name)
        installed = ((self.folder / pack["name"]).exists() or (self.folder / pack["name"]).is_symlink()
                     or (self.folder / (pack["name"] + ".disabled")).exists()
                     or (self.folder / (pack["name"] + ".disabled")).is_symlink())
        status = QLabel("●  In this client" if from_library and installed else
                        "●  Available" if pack["enabled"] and not from_library else
                        "○  Hidden" if not from_library else "○  In your library")
        status.setObjectName("active" if pack["enabled"] else "inactive")
        badges = QHBoxLayout()
        badges.setSpacing(10)
        badges.addWidget(status)
        source = (DEFAULT_LIBRARY if from_library else self.folder) / pack["name"]
        number = pack_format(source)
        expected = self.selected_version()
        supports = pack_supports(source, expected)
        compatibility = QLabel(
            f"Format {number} · {'✓ supports ' + expected if supports else '⚠ different from ' + expected}"
            if number is not None and expected is not None and supports is not None else
            f"Format {number}" if number is not None else "Unknown pack format")
        compatibility.setObjectName("active" if supports else "inactive")
        badges.addWidget(compatibility)
        badges.addStretch()
        info.addLayout(badges)
        tested = self.settings.get("tested_packs", {}).get(str(source.resolve()))
        try:
            fingerprint = source.stat()
        except OSError:
            fingerprint = None
        if (tested and fingerprint and tested.get("version") == self.selected_version() and
                tested.get("size") == fingerprint.st_size and
                tested.get("modified") == fingerprint.st_mtime_ns):
            note = QLabel(f"✓ Tested in-game for {tested['version']} (self-reported)")
            note.setObjectName("active")
            info.addWidget(note)
        description = QLabel(re.sub(r"§.", "", pack["description"]))
        description.setObjectName("description")
        description.setWordWrap(True)
        description.setMaximumHeight(35)
        info.addWidget(description)
        row.addLayout(info, 1)
        outer.addLayout(row)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        preview = AnimatedButton("◉  Preview")
        preview.clicked.connect(lambda checked=False, p=source: self.preview_pack(p))
        actions.addWidget(preview)
        if pack["kind"] == "zip" and self.selected_version() and supports is False:
            convert = AnimatedButton(f"↔  Convert to {self.selected_version()}")
            convert.clicked.connect(lambda checked=False, p=source: self.convert_for_client(p))
            actions.addWidget(convert)
        actions.addStretch()
        if from_library:
            if pack["kind"] == "zip" and not installed:
                install = AnimatedButton("Install →")
                install.setObjectName("primary")
                install.clicked.connect(lambda checked=False, n=pack["name"]: self.install_pack(n))
                actions.addWidget(install)
        elif pack["kind"] == "zip":
            action = AnimatedButton("Hide" if pack["enabled"] else "Show")
            action.setObjectName("primary" if not pack["enabled"] else "")
            action.clicked.connect(lambda checked=False, n=pack["name"]: self.toggle_pack(n))
            actions.addWidget(action)
        more = QToolButton()
        more.setText("More  ···")
        more.setToolTip("More actions for this pack")
        menu = QMenu(more)
        menu.addAction("✓  In-game checklist", lambda checked=False, n=pack["name"], p=source:
                       self.show_test_checklist(n, p))
        if pack["kind"] == "zip" and self.selected_version():
            menu.addAction(f"↔  Convert to {self.selected_version()}",
                           lambda checked=False, p=source: self.convert_for_client(p))
        if not from_library:
            menu.addAction("▣  Back up this pack", lambda checked=False, n=pack["name"]: self.backup_pack(n))
        elif pack["kind"] == "zip":
            tracked = self.settings.get("tracked_updates", {}).get(pack["name"])
            menu.addSeparator()
            menu.addAction("↻  Edit tracking" if tracked else "↻  Track updates",
                           lambda checked=False, n=pack["name"]: self.track_updates(n))
            if tracked:
                menu.addAction("Stop tracking", lambda checked=False, n=pack["name"]: self.stop_tracking(n))
            if pack["name"] in self.settings.get("update_rollback", {}):
                menu.addAction("↶  Restore previous", lambda checked=False, n=pack["name"]: self.rollback_update(n))
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        actions.addWidget(more)
        outer.addLayout(actions)
        return card

    def preview_pack(self, source):
        pictures = texture_previews(source)
        if not pictures:
            return self.notify("No previewable PNG textures found")
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Preview · {source.name}")
        dialog.resize(565, 420)
        layout = QVBoxLayout(dialog)
        title = QLabel(f"{source.name} · sample textures")
        title.setObjectName("hello")
        layout.addWidget(title)
        note = QLabel("Sample images from the ZIP, not a full in-game render.")
        note.setObjectName("sub")
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        for i, (filename, raw) in enumerate(pictures):
            image = QPixmap()
            if not image.loadFromData(raw, "PNG"):
                continue
            tile = QFrame()
            tile.setObjectName("panel")
            part = QVBoxLayout(tile)
            thumbnail = QLabel()
            thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumbnail.setPixmap(image.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.FastTransformation))
            part.addWidget(thumbnail)
            label = QLabel(filename.rsplit("/", 1)[-1])
            label.setObjectName("description")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            part.addWidget(label)
            grid.addWidget(tile, i // 3, i % 3)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        dialog.exec()

    def show_test_checklist(self, name, source=None):
        version = self.selected_version()
        if not version:
            return self.error("Choose your Minecraft version before testing a pack")
        source = source or self.folder / name
        dialog = QDialog(self)
        dialog.setWindowTitle(f"In-game test · {name}")
        dialog.resize(520, 330)
        layout = QVBoxLayout(dialog)
        heading = QLabel(f"Test {name} in Minecraft {version}")
        heading.setObjectName("hello")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        explanation = QLabel("Pack Vault cannot verify textures in-game. Check these yourself, then mark it tested. "
                             "If something looks wrong, unselect the copy; your original is unchanged.")
        explanation.setObjectName("sub")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        checks = []
        for step in (
            "Launch this Minecraft version and select the pack.",
            "Check blocks and items for missing textures.",
            "Check armor, entities and custom models.",
            "Check inventory, menus, fonts and shaders.",
            "Check pack order; keep the original for rollback.",
        ):
            box = QCheckBox(step)
            layout.addWidget(box)
            checks.append(box)
        layout.addStretch()
        actions = QHBoxLayout()
        done = AnimatedButton("Mark tested (self-reported)")
        done.setEnabled(False)
        for check in checks:
            check.toggled.connect(lambda: done.setEnabled(all(item.isChecked() for item in checks)))
        done.clicked.connect(dialog.accept)
        actions.addWidget(done)
        dismiss = AnimatedButton("Close")
        dismiss.clicked.connect(dialog.reject)
        actions.addWidget(dismiss)
        layout.addLayout(actions)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                stat = source.stat()
            except OSError as exc:
                return self.error(exc)
            self.settings.setdefault("tested_packs", {})[str(source.resolve())] = {
                "version": version, "date": datetime.now().isoformat(timespec="seconds"),
                "size": stat.st_size, "modified": stat.st_mtime_ns}
            self.save_settings()
            self.render()
            self.notify(f"Marked {name} tested in {version} · self-reported")

    def convert_for_client(self, source):
        version = self.selected_version()
        if not version:
            return self.error("Choose your Minecraft version first")
        answer = QMessageBox.question(self, "Best-effort conversion",
            f"Create a NEW copy of {source.name} for Minecraft {version}? This changes pack.mcmeta and adds "
            "legacy block/item texture aliases when relevant. It cannot convert every changed model, shader, "
            "sound, or texture. The original will remain untouched.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            report = {}
            destination = convert_pack(source, version, DEFAULT_LIBRARY, report=report)
            installed = False
            try:
                install_from_library(destination.name, self.folder, DEFAULT_LIBRARY)
            except (OSError, ValueError):
                self.notify(f"Converted copy saved in library: {destination.name}")
            else:
                installed = True
                self.notify(f"Created and installed {destination.name} · test it in Minecraft")
            self.reload()
            self.show_conversion_report(destination.name, report, installed)
        except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            self.error(exc)

    def show_conversion_report(self, name, report, installed):
        untouched = report["unchanged"]
        examples = "\n".join("  + " + path for path in report["aliases"][:5])
        summary = (f"Created {name} (format {report['source_format']} → {report['target_format']}).\n"
                   f"Texture path aliases added: {len(report['aliases'])}; collisions skipped: "
                   f"{report['alias_collisions']}." +
                   (f"\nExamples:\n{examples}" if examples else "") + "\n"
                   f"Overlays removed: {'yes' if report['removed_overlays'] else 'no'}.\n"
                   f"Copied without conversion: {untouched['models']} models, "
                   f"{untouched['shaders']} shader files, {untouched['sounds']} sound files.\n\n"
                   "Metadata and path aliases cannot guarantee in-game compatibility. "
                   "Original ZIP stays untouched." +
                   ("\n\nOpen the in-game checklist?" if installed else "\n\nInstall the copy to test it."))
        if installed and QMessageBox.question(self, "Conversion report", summary) == QMessageBox.StandardButton.Yes:
            self.show_test_checklist(name)
        elif not installed:
            QMessageBox.information(self, "Conversion report", summary)

    def error(self, message):
        QMessageBox.warning(self, "Pack Vault", str(message))

    def notify(self, message):
        if self._toast is not None:
            self._toast.deleteLater()
        toast = QFrame(self.centralWidget())
        toast.setObjectName("toast")
        row = QHBoxLayout(toast)
        row.setContentsMargins(17, 12, 17, 12)
        text = QLabel("✦  " + message)
        text.setMinimumWidth(250)
        text.setMaximumWidth(345)
        text.setWordWrap(True)
        row.addWidget(text)
        toast.setMinimumWidth(300)
        toast.adjustSize()
        target = QPoint(self.centralWidget().width() - toast.width() - 24,
                        self.centralWidget().height() - toast.height() - 75)
        toast.move(target + QPoint(0, 75))
        toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        effect = QGraphicsOpacityEffect(toast)
        effect.setOpacity(0)
        toast.setGraphicsEffect(effect)
        toast.show()
        toast.raise_()
        slide = QPropertyAnimation(toast, b"pos", toast)
        slide.setStartValue(target + QPoint(0, 75))
        slide.setEndValue(target)
        slide.setDuration(320)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(effect, b"opacity", toast)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(260)
        animation = QParallelAnimationGroup(toast)
        animation.addAnimation(slide)
        animation.addAnimation(fade)
        animation.start()
        self._toast = toast
        self.toast_animation = animation
        timer = QTimer(toast)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.dismiss_toast(toast, effect))
        timer.start(3000)

    def dismiss_toast(self, toast, effect):
        if toast is not self._toast:
            return
        fade = QPropertyAnimation(effect, b"opacity", toast)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setDuration(440)
        fade.finished.connect(toast.deleteLater)
        fade.finished.connect(lambda: setattr(self, "_toast", None))
        self.toast_animation = fade
        fade.start()

    def install_pack(self, name):
        try:
            install_from_library(name, self.folder)
            self.reload()
            self.notify(f"Installed {name} to {self.client_box.currentText()}")
        except (OSError, ValueError) as exc:
            self.error(exc)

    def toggle_pack(self, name):
        try:
            toggle(self.folder, name)
            self.reload()
            self.notify(f"Updated {name}")
        except (OSError, ValueError) as exc:
            self.error(exc)

    def backup_pack(self, name):
        try:
            source = self.folder / name
            backups = self.folder.parent / "pack-vault-backups"
            backups.mkdir(exist_ok=True)
            destination = backups / name
            index = 1
            while destination.exists() or destination.is_symlink():
                destination = backups / f"{name}.{index}"
                index += 1
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            self.notify(f"Backup saved: {destination.name}")
        except OSError as exc:
            self.error(exc)

    def import_pack(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Choose a resource pack", str(Path.home() / "Downloads"),
                                                   "Resource packs (*.zip)")
        if not filename:
            return
        self.import_files([Path(filename)])

    def open_library(self):
        DEFAULT_LIBRARY.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DEFAULT_LIBRARY)))

    def pick_pack(self):
        packs = list_packs(DEFAULT_LIBRARY) if self.tabs.currentIndex() == 2 else self.packs
        available = [p for p in packs if p["enabled"]]
        if available:
            if self.tabs.currentIndex() in (0, 3):
                self.tabs.setCurrentIndex(1)
            self.search.setText(random.choice(available)["name"])
            self.notify("Found you a pack ✦")
        else:
            self.error("No packs to pick from yet!")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        for asset in ("icon.svg", "chevron.svg"):
            if not asset_path(asset).is_file():
                raise SystemExit(f"Missing bundled asset: {asset}")
        app = QApplication([sys.argv[0]])
        window = PackVault()
        if window.tabs.count() != 5:
            raise SystemExit("GUI failed to initialize")
        window.close()
        raise SystemExit(0)
    app = QApplication(sys.argv)
    window = PackVault()
    window.show()
    sys.exit(app.exec())
