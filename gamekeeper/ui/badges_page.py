"""The BADGES page: your GameKeeper level and every game's badge."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .. import badges
from ..storage import Game
from . import badge_art, style
from .flow import FlowLayout


class BadgeCard(QWidget):
    clicked = Signal(str)

    def __init__(self, game: Game, ready: int):
        super().__init__()
        self.game_id = game.id
        self.setObjectName("BadgeCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(170, 190)
        lvl = min(game.badge_level, badges.MAX_LEVEL)
        border = style.ACCENT if ready else style.BORDER
        self.setStyleSheet(f"#BadgeCard {{ background: {style.PANEL}; border: 1px solid {border}; border-radius: 3px; }}"
                           f"#BadgeCard:hover {{ background: {style.PANEL_2}; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 12, 10, 10)
        v.setSpacing(4)
        img = QLabel()
        img.setFixedSize(96, 96)
        img.setAlignment(Qt.AlignCenter)
        img.setPixmap(badge_art.badge_pixmap(game, max(lvl, 1), 96, locked=lvl == 0))
        v.addWidget(img, 0, Qt.AlignHCenter)
        name = QLabel(badge_art.level_name(game, lvl) if lvl else "Not crafted yet")
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet(f"color: {style.TEXT_BRIGHT if lvl else style.MUTED}; font-weight: 600;")
        v.addWidget(name)
        title = QLabel(game.name)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {style.MUTED}; font-size: 12px;")
        title.setText(title.fontMetrics().elidedText(game.name, Qt.ElideRight, 150))
        v.addWidget(title)
        meta = QLabel(f"Level {lvl} / {badges.MAX_LEVEL}" + (f"  ·  {ready} ready" if ready else ""))
        meta.setAlignment(Qt.AlignCenter)
        meta.setStyleSheet(f"color: {style.ACCENT if ready else style.MUTED}; font-size: 11px; font-weight: 700;")
        v.addWidget(meta)
        v.addStretch()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.game_id)


class BadgesPage(QWidget):
    open_badge = Signal(str)     # game id

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        self.v = QVBoxLayout(body)
        self.v.setContentsMargins(26, 20, 26, 26)
        self.v.setSpacing(16)

        head = QWidget()
        head.setObjectName("Card")
        head.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        h = QHBoxLayout(head)
        h.setContentsMargins(20, 16, 20, 16)
        h.setSpacing(18)
        self.ring = QLabel()
        self.ring.setFixedSize(84, 84)
        h.addWidget(self.ring)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.level_label = QLabel()
        self.level_label.setStyleSheet(f"color: {style.TEXT_BRIGHT}; font-size: 20px; font-weight: 700;")
        self.xp_label = QLabel()
        self.xp_label.setStyleSheet(f"color: {style.MUTED};")
        self.xp_bar = QProgressBar()
        self.xp_bar.setTextVisible(False)
        self.xp_bar.setFixedHeight(6)
        self.summary = QLabel()
        self.summary.setStyleSheet(f"color: {style.MUTED}; font-size: 12px;")
        info.addWidget(self.level_label)
        info.addWidget(self.xp_label)
        info.addWidget(self.xp_bar)
        info.addWidget(self.summary)
        h.addLayout(info, 1)
        self.v.addWidget(head)

        self.section = QLabel("BADGES")
        self.section.setStyleSheet(f"color: {style.TEXT_BRIGHT}; font-size: 14px; font-weight: 700; letter-spacing: 1px;")
        self.v.addWidget(self.section)
        self.grid_host = QWidget()
        self.flow = FlowLayout(self.grid_host, spacing=12)
        self.v.addWidget(self.grid_host)
        self.empty = QLabel("Pull achievements for a game, earn some, and craft its badge from the game's BADGE tab.")
        self.empty.setStyleSheet(f"color: {style.MUTED};")
        self.v.addWidget(self.empty)
        self.v.addStretch()

    def refresh(self, games: list[Game]):
        xp = badges.profile_xp(games)
        level, into, need = badges.profile_level(xp)
        self.ring.setPixmap(badge_art.level_ring(level, 84))
        self.level_label.setText(f"GameKeeper level {level}")
        self.xp_label.setText(f"{xp} XP  ·  {need - into} XP to level {level + 1}")
        self.xp_bar.setMaximum(need)
        self.xp_bar.setValue(into)
        crafted = sum(min(g.badge_level, badges.MAX_LEVEL) for g in games)
        maxed = sum(1 for g in games if g.badge_level >= badges.MAX_LEVEL)
        self.summary.setText(f"{crafted} badge level(s) crafted  ·  {maxed} badge(s) at max level")

        while self.flow.count():
            w = self.flow.takeAt(0).widget()
            if w:
                w.deleteLater()
        shown = []
        for g in games:
            if not g.achievements_total and not g.badge_level:
                continue
            ready = badges.craftable_levels(g)
            shown.append((-ready, -g.badge_level, g.name.lower(), g, ready))
        for *_, g, ready in sorted(shown, key=lambda t: t[:3]):
            card = BadgeCard(g, ready)
            card.clicked.connect(self.open_badge)
            self.flow.addWidget(card)
        self.empty.setVisible(not shown)
        self.grid_host.updateGeometry()
