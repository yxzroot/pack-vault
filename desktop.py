#!/usr/bin/env python3
"""Pack Vault — a native resource-pack manager for Minecraft clients."""

import json
import getpass
import random
import re
import shutil
import sys
import math
from urllib.error import URLError
from pathlib import Path
import zipfile

from PySide6.QtCore import (Property, QEasingCurve, QParallelAnimationGroup, QPauseAnimation,
                            QPoint, QPropertyAnimation, QSequentialAnimationGroup, Qt, QTimer, QUrl,
                            QVariantAnimation, QThread, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QInputDialog, QLineEdit,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

from app import (DEFAULT_LIBRARY, DEFAULT_PACKS, app_directories, asset_path, discover_clients,
                  import_pack, install_from_library, list_packs, pack_data, toggle)
from features import (apply_profile, enabled_zip_names, latest_modrinth_version, modrinth_slug,
                      scan_conflicts)


SETTINGS = app_directories()[1] / "settings.json"
THEMES = {
    "Midnight": ("#11101b", "#211d30", "#403653", "#bf99fc", "#f4efff", "#a6a0b8"),
    "Sakura": ("#211720", "#34232f", "#674159", "#f5a6c9", "#fff0f5", "#c8a6b8"),
    "Forest": ("#101c19", "#1c2d28", "#385a4e", "#9ce0b0", "#edf9f1", "#9dbbaa"),
    "Daylight": ("#f2eff9", "#ffffff", "#d7cce8", "#7752ad", "#271e33", "#71667e"),
    "Apple": ("#f5f5f7", "#ffffff", "#d2d2d7", "#007aff", "#1d1d1f", "#6e6e73"),
}


def stylesheet(theme):
    bg, surface, border, accent, text, muted = THEMES[theme]
    font = "'Inter', 'Noto Sans', 'Sans Serif'" if theme == "Apple" else "'Sans Serif'"
    return f"""
    QWidget {{ background: {bg}; color: {text}; font-family: {font}; font-size: 14px; }}
    QLabel#eyebrow, QLabel#count {{ color: {accent}; font-weight: bold; }}
    QLabel#eyebrow {{ font-size: 11px; letter-spacing: 1px; }}
    QLabel#title {{ font-size: 38px; font-weight: 800; }}
    QLabel#hello {{ font-size: 29px; font-weight: 800; }}
    QLabel#stat {{ font-size: 30px; font-weight: 800; color: {accent}; }}
    QLabel#sub, QLabel#path, QLabel#description, QLabel#hint {{ color: {muted}; }}
    QLabel#path {{ font-size: 11px; }}
    QFrame#card, QFrame#panel {{ background: {surface}; border: 1px solid {border}; border-radius: 22px; }}
    QFrame#card QLabel, QFrame#panel QLabel, QFrame#hero QLabel {{ background: transparent; }}
    QLabel#packname {{ font-size: 17px; font-weight: bold; }}
    QLabel#active {{ color: {accent}; font-size: 12px; font-weight: bold; }}
    QLabel#inactive {{ color: {muted}; font-size: 12px; font-weight: bold; }}
    QFrame#toast {{ background: {accent}; border-radius: 18px; }}
    QFrame#toast QLabel {{ color: {bg}; background: transparent; font-weight: bold; }}
    QLineEdit, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 16px;
                          padding: 11px 15px; min-height: 19px; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url("{asset_path('chevron.svg').as_posix()}"); width: 12px; height: 9px; }}
    QComboBox QAbstractItemView {{ background: {surface}; color: {text}; selection-background-color: {border};
                                  border: 1px solid {border}; border-radius: 14px; padding: 6px; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
    QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 16px;
                   padding: 10px 16px; font-weight: bold; }}
    QPushButton#primary {{ background: {accent}; color: {bg}; border-color: {accent}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ padding: 10px 22px; margin: 3px; border: 1px solid transparent;
                    border-radius: 15px; color: {muted}; }}
    QTabBar::tab:selected {{ color: {accent}; background: {surface}; border-color: {border}; }}
    QTabBar::tab:hover {{ color: {accent}; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 0; }}
    QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 32px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 10px; padding: 8px; }}
    """


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
        self.ripple_animation.setDuration(720)
        self.ripple_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ripple_animation.valueChanged.connect(self.set_ripple)
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setDuration(300)
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
        animation.setDuration(360)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        if not highlighted:
            animation.finished.connect(lambda: self.setGraphicsEffect(None) if not self._hovered else None)
        self.shadow_animation = animation
        animation.start()


class WelcomeTour(QDialog):
    STEPS = [
        ("✦", "Welcome to Pack Vault", "Keep your Minecraft texture packs together and use them across clients. Let's take a quick look around."),
        ("⌄", "Choose your client", "Pick a detected Minecraft client at the top. Don't see yours? Use Add folder to choose its resourcepacks directory."),
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
            animation.setDuration(560)
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

    def __init__(self, projects, parent=None):
        super().__init__(parent)
        self.projects = projects

    def run(self):
        versions, errors = {}, {}
        for name, slug in self.projects.items():
            if self.isInterruptionRequested():
                break
            try:
                versions[name] = latest_modrinth_version(slug)
            except (ValueError, OSError, URLError, KeyError, TypeError) as exc:
                errors[name] = str(exc)
        if not self.isInterruptionRequested():
            self.checked.emit((versions, errors))


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
        self.number_animations = []
        self.stat_targets = [0, 0, 0]
        self._active_tab = 0
        self._page_animation = None
        self._moving_page = None
        self._page_home = None
        self._toast = None
        self.toast_animation = None
        self.update_worker = None
        self.update_mode = None
        self.setAcceptDrops(True)
        self.setWindowTitle("Pack Vault · Minecraft resource packs")
        self.setWindowIcon(QIcon(str(asset_path("icon.svg"))))
        self.resize(980, 860)
        self.setMinimumSize(650, 560)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(10)
        eyebrow = QLabel("✦   YOUR MINECRAFT PACKS, EVERYWHERE")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Pack Vault.")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("One library. Any Minecraft client. Pick a client and install with a click.")
        subtitle.setObjectName("sub")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        controls = QFrame()
        controls.setObjectName("panel")
        control_layout = QVBoxLayout(controls)
        control_layout.setContentsMargins(16, 16, 16, 16)
        top = QHBoxLayout()
        top.addWidget(QLabel("Minecraft client"))
        self.client_box = QComboBox()
        self.client_box.setMinimumWidth(200)
        self.client_box.currentIndexChanged.connect(self.change_client)
        top.addWidget(self.client_box, 1)
        add_client = AnimatedButton("＋  Add folder")
        add_client.clicked.connect(self.add_client)
        top.addWidget(add_client)
        refresh = AnimatedButton("↻")
        refresh.setToolTip("Find newly installed Minecraft clients")
        refresh.clicked.connect(lambda: self.refresh_clients(manual=True))
        top.addWidget(refresh)
        top.addWidget(QLabel("Theme"))
        self.theme_box = QComboBox()
        self.theme_box.addItems(THEMES)
        self.theme_box.setCurrentText(self.settings.get("theme", "Midnight") if
                                      self.settings.get("theme") in THEMES else "Midnight")
        self.theme_box.currentTextChanged.connect(self.change_theme)
        top.addWidget(self.theme_box)
        control_layout.addLayout(top)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("path")
        self.folder_label.setWordWrap(True)
        control_layout.addWidget(self.folder_label)
        layout.addWidget(controls)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search packs…")
        self.search.textChanged.connect(lambda _text: self.render())
        toolbar.addWidget(self.search, 1)
        pick = AnimatedButton("✦  Surprise me")
        pick.clicked.connect(self.pick_pack)
        toolbar.addWidget(pick)
        import_button = AnimatedButton("＋  Import ZIP")
        import_button.setObjectName("primary")
        import_button.clicked.connect(self.import_pack)
        toolbar.addWidget(import_button)
        layout.addLayout(toolbar)

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Drop ZIPs here to import  ·"))
        check_conflicts = AnimatedButton("Scan overlaps")
        check_conflicts.clicked.connect(self.show_conflicts)
        tools.addWidget(check_conflicts)
        check_updates = AnimatedButton("Check updates")
        check_updates.clicked.connect(self.check_updates)
        tools.addWidget(check_updates)
        tools.addStretch()
        layout.addLayout(tools)

        self.count = QLabel()
        self.count.setObjectName("count")
        layout.addWidget(self.count)
        self.tabs = QTabWidget()
        self.cards = []
        self.tabs.currentChanged.connect(self.on_tab_changed)
        dashboard = QWidget()
        overview = QVBoxLayout(dashboard)
        overview.setContentsMargins(8, 12, 8, 12)
        overview.setSpacing(8)
        self.hero = AnimatedHero()
        self.hero.setMinimumHeight(80)
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(26, 22, 26, 22)
        self.greeting = QLabel(f"Hey, {getpass.getuser()}! 👋")
        self.greeting.setObjectName("hello")
        hero_layout.addWidget(self.greeting)
        welcome = QLabel("Welcome back. Here's your corner of the Minecraft universe.")
        welcome.setObjectName("sub")
        hero_layout.addWidget(welcome)
        overview.addWidget(self.hero)
        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_labels = []
        for caption in ("CLIENTS", "IN THIS CLIENT", "IN YOUR LIBRARY"):
            tile = QFrame()
            tile.setObjectName("panel")
            tile.setMinimumHeight(75)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(20, 18, 20, 18)
            value = QLabel("0")
            value.setObjectName("stat")
            tile_layout.addWidget(value)
            label = QLabel(caption)
            label.setObjectName("eyebrow")
            tile_layout.addWidget(label)
            stats.addWidget(tile, 1)
            self.stat_labels.append(value)
        overview.addLayout(stats)
        latest_panel = QFrame()
        latest_panel.setObjectName("panel")
        latest_panel.setMinimumHeight(124)
        latest_layout = QVBoxLayout(latest_panel)
        latest_layout.setContentsMargins(22, 18, 22, 18)
        latest_heading = QLabel("✦  READY WHEN YOU ARE")
        latest_heading.setObjectName("eyebrow")
        latest_layout.addWidget(latest_heading)
        self.dashboard_tip = QLabel()
        self.dashboard_tip.setObjectName("sub")
        self.dashboard_tip.setWordWrap(True)
        latest_layout.addWidget(self.dashboard_tip)
        actions = QHBoxLayout()
        import_quick = AnimatedButton("＋  Import a pack")
        import_quick.setObjectName("primary")
        import_quick.clicked.connect(self.import_pack)
        actions.addWidget(import_quick)
        library_quick = AnimatedButton("Browse library →")
        library_quick.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        actions.addWidget(library_quick)
        tour_quick = AnimatedButton("Take the tour")
        tour_quick.clicked.connect(self.show_tour)
        actions.addWidget(tour_quick)
        actions.addStretch()
        latest_layout.addLayout(actions)
        overview.addWidget(latest_panel)
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
        layout.addWidget(self.tabs, 1)
        bottom = QHBoxLayout()
        hint = QLabel("Imported packs are stored safely in your library. Existing packs are never replaced.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        bottom.addWidget(hint, 1)
        open_library = AnimatedButton("Open library ↗")
        open_library.clicked.connect(self.open_library)
        bottom.addWidget(open_library)
        layout.addLayout(bottom)
        self.populate_clients()
        self.change_theme(self.theme_box.currentText())
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
        self.settings["theme"] = theme
        self.save_settings()
        self.render()

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
        self.folder_label.setText(f"Resourcepacks → {self.folder}")
        self.settings["client"] = path
        self.save_settings()
        self.reload()

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
        self.hero.set_motion(index == 0 and self.isVisible())
        self.render(animate=True)
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
        start = origin + QPoint(direction * 100, 0)
        self._moving_page = page
        self._page_home = origin
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        page.move(start)
        slide = QPropertyAnimation(page, b"pos", page)
        slide.setStartValue(start)
        slide.setEndValue(origin)
        slide.setDuration(690)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade = QPropertyAnimation(effect, b"opacity", page)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(620)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation = QParallelAnimationGroup(page)
        animation.addAnimation(slide)
        animation.addAnimation(fade)
        animation.finished.connect(self.finish_tab_animation)
        self._page_animation = animation
        animation.start()

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

    def animate_cards(self, visible_cards):
        for animation in self.card_animations:
            animation.stop()
        self.card_animations.clear()
        for i, card in enumerate(visible_cards[:8]):
            height = card.sizeHint().height()
            effect = QGraphicsOpacityEffect(card)
            effect.setOpacity(0)
            card.setGraphicsEffect(effect)
            card.setMaximumHeight(0)
            fade = QPropertyAnimation(effect, b"opacity", card)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setDuration(530)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            expand = QPropertyAnimation(card, b"maximumHeight", card)
            expand.setStartValue(0)
            expand.setEndValue(height + 8)
            expand.setDuration(610)
            expand.setEasingCurve(QEasingCurve.Type.OutCubic)
            together = QParallelAnimationGroup(card)
            together.addAnimation(fade)
            together.addAnimation(expand)
            sequence = QSequentialAnimationGroup(card)
            sequence.addAnimation(QPauseAnimation(i * 95, card))
            sequence.addAnimation(together)
            sequence.finished.connect(lambda c=card: self.finish_card_animation(c))
            sequence.start()
            self.card_animations.append(sequence)

    @staticmethod
    def finish_card_animation(card):
        card.setMaximumHeight(16777215)
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
        self.dashboard_tip.setText(
            f"{self.client_box.currentText()} has {len(self.packs)} pack(s). Import a ZIP or browse your library to add more."
            if library or self.packs else "Import your first ZIP to start your pack collection.")
        if tab == 0:
            return
        if tab == 3:
            self.render_profiles()
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
        if active:
            deactivate = AnimatedButton("Deactivate profile ↶")
            deactivate.clicked.connect(self.deactivate_profile)
            row.addWidget(deactivate)
        row.addStretch()
        layout.addLayout(row)
        self.profile_cards.addWidget(header)
        for name, packs in sorted(saved.items()):
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
            remove = AnimatedButton("Remove")
            remove.clicked.connect(lambda checked=False, n=name: self.remove_profile(n))
            line.addWidget(remove)
            self.profile_cards.addWidget(card)

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
        profiles[name] = enabled_zip_names(self.folder)
        self.save_settings()
        self.render_profiles()
        self.notify(f"Saved profile {name}")

    def activate_profile(self, name):
        path = str(self.folder)
        wanted = self.settings.get("profiles", {}).get(path, {}).get(name)
        if wanted is None:
            return self.error("Profile not found")
        current = self.settings.get("active_profiles", {}).get(path)
        previous = self.settings.get("profile_previous", {}).get(path)
        before = enabled_zip_names(self.folder)
        try:
            apply_profile(self.folder, wanted, DEFAULT_LIBRARY)
        except (ValueError, OSError) as exc:
            return self.error(exc)
        if not current or previous is None:
            self.settings.setdefault("profile_previous", {})[path] = before
        self.settings.setdefault("active_profiles", {})[path] = name
        self.save_settings()
        self.reload()
        self.notify(f"Activated {name}")

    def deactivate_profile(self):
        path = str(self.folder)
        previous = self.settings.get("profile_previous", {}).get(path)
        if previous is None:
            return self.error("No previous pack selection was saved")
        try:
            apply_profile(self.folder, previous, DEFAULT_LIBRARY)
        except (OSError, ValueError) as exc:
            return self.error(exc)
        self.settings.get("active_profiles", {}).pop(path, None)
        self.settings.get("profile_previous", {}).pop(path, None)
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
        worker = UpdateWorker(projects, self)
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
                self.settings.setdefault("tracked_updates", {})[name] = {
                    "slug": projects[name], "id": version["id"]}
            if versions:
                self.save_settings()
                self.notify("Update tracking enabled — current version saved as baseline")
                self.render()
        else:
            updated = [f"{name}: {version['number']}\n{version['url']}" for name, version in versions.items()
                       if version["id"] != self.settings.get("tracked_updates", {}).get(name, {}).get("id")]
            if updated:
                QMessageBox.information(self, "Updates available", "New Modrinth versions:\n\n" + "\n\n".join(updated))
            elif not errors:
                self.notify("No new releases since tracking began")
        if errors:
            QMessageBox.warning(self, "Update check", "Could not check:\n" + "\n".join(f"{n}: {e}" for n, e in errors.items()))

    def closeEvent(self, event):
        if self.update_worker is not None and self.update_worker.isRunning():
            self.update_worker.requestInterruption()
            self.update_worker.wait(17000)
        super().closeEvent(event)

    def card(self, pack, from_library):
        card = AnimatedCard()
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 16, 18, 16)
        row.setSpacing(17)
        icon = QLabel("✦")
        icon.setFixedSize(66, 66)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accent = THEMES[self.theme_box.currentText()][3]
        icon.setStyleSheet(f"font-size: 32px; color: {accent}; border-radius: 10px")
        if pack["icon"]:
            image = pack_data((DEFAULT_LIBRARY if from_library else self.folder) / pack["name"])[1]
            pixmap = QPixmap()
            if image and pixmap.loadFromData(image, "PNG"):
                icon.setPixmap(pixmap.scaled(66, 66, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.FastTransformation))
        row.addWidget(icon)
        info = QVBoxLayout()
        name = QLabel(pack["name"].removesuffix(".disabled").removesuffix(".zip"))
        name.setObjectName("packname")
        info.addWidget(name)
        installed = ((self.folder / pack["name"]).exists() or (self.folder / pack["name"]).is_symlink()
                     or (self.folder / (pack["name"] + ".disabled")).exists()
                     or (self.folder / (pack["name"] + ".disabled")).is_symlink())
        status = QLabel("●  In this client" if from_library and installed else
                        "●  Available" if pack["enabled"] and not from_library else
                        "○  Hidden" if not from_library else "○  In your library")
        status.setObjectName("active" if pack["enabled"] else "inactive")
        info.addWidget(status)
        description = QLabel(re.sub(r"§.", "", pack["description"]))
        description.setObjectName("description")
        description.setWordWrap(True)
        description.setMaximumHeight(45)
        info.addWidget(description)
        row.addLayout(info, 1)
        actions = QVBoxLayout()
        if from_library:
            if pack["kind"] == "zip" and not installed:
                install = AnimatedButton("Install →")
                install.setObjectName("primary")
                install.clicked.connect(lambda checked=False, n=pack["name"]: self.install_pack(n))
                actions.addWidget(install)
            if pack["kind"] == "zip":
                tracked = self.settings.get("tracked_updates", {}).get(pack["name"])
                track = AnimatedButton("Edit tracking" if tracked else "Track updates")
                track.clicked.connect(lambda checked=False, n=pack["name"]: self.track_updates(n))
                actions.addWidget(track)
                if tracked:
                    stop = AnimatedButton("Stop tracking")
                    stop.clicked.connect(lambda checked=False, n=pack["name"]: self.stop_tracking(n))
                    actions.addWidget(stop)
        elif pack["kind"] == "zip":
            action = AnimatedButton("Hide" if pack["enabled"] else "Show")
            action.clicked.connect(lambda checked=False, n=pack["name"]: self.toggle_pack(n))
            actions.addWidget(action)
        if not from_library:
            backup = AnimatedButton("Backup")
            backup.clicked.connect(lambda checked=False, n=pack["name"]: self.backup_pack(n))
            actions.addWidget(backup)
        row.addLayout(actions)
        return card

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
        slide.setDuration(650)
        slide.setEasingCurve(QEasingCurve.Type.OutBack)
        fade = QPropertyAnimation(effect, b"opacity", toast)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(540)
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
            while destination.exists():
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
        if window.tabs.count() != 4:
            raise SystemExit("GUI failed to initialize")
        window.close()
        raise SystemExit(0)
    app = QApplication(sys.argv)
    window = PackVault()
    window.show()
    sys.exit(app.exec())
