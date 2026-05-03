"""Read-only code editor with Pygments-driven syntax highlighting + line numbers."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor, QFont, QFontDatabase, QPainter, QPaintEvent, QSyntaxHighlighter,
    QTextCharFormat, QTextDocument, QResizeEvent,
)
from PyQt6.QtWidgets import QPlainTextEdit, QWidget

# Pygments
try:
    from pygments import lex
    from pygments.lexers.hdl import VerilogLexer
    try:
        from pygments.lexers.spice import SpiceLexer  # newer pygments
    except Exception:  # pragma: no cover
        SpiceLexer = None
    from pygments.token import Token
except Exception:  # pragma: no cover
    lex = None
    VerilogLexer = None
    SpiceLexer = None
    Token = None


# Token → color map per theme (Catppuccin Mocha for dark, GitHub Light for light)
_PALETTE_DARK = {
    "Token.Keyword": "#cba6f7",
    "Token.Keyword.Type": "#89b4fa",
    "Token.Name.Builtin": "#89dceb",
    "Token.Name.Class": "#f9e2af",
    "Token.Name.Function": "#f5c2e7",
    "Token.Name.Variable": "#cdd6f4",
    "Token.Name": "#cdd6f4",
    "Token.Literal.Number": "#fab387",
    "Token.Literal.String": "#a6e3a1",
    "Token.Comment": "#6c7086",
    "Token.Comment.Single": "#6c7086",
    "Token.Operator": "#f38ba8",
    "Token.Punctuation": "#cdd6f4",
}
_PALETTE_LIGHT = {
    "Token.Keyword": "#8250df",
    "Token.Keyword.Type": "#0550ae",
    "Token.Name.Builtin": "#0550ae",
    "Token.Name.Class": "#953800",
    "Token.Name.Function": "#8250df",
    "Token.Name.Variable": "#24292f",
    "Token.Name": "#24292f",
    "Token.Literal.Number": "#0550ae",
    "Token.Literal.String": "#0a3069",
    "Token.Comment": "#6e7781",
    "Token.Comment.Single": "#6e7781",
    "Token.Operator": "#cf222e",
    "Token.Punctuation": "#24292f",
}
# Active palette (mutable, updated by apply_theme)
_PALETTE = dict(_PALETTE_DARK)


_THEME_EDITOR_STYLE = {
    "dark": (
        "QPlainTextEdit { background: #11111b; color: #cdd6f4; "
        "border: 1px solid #313244; padding: 4px; }"
    ),
    "light": (
        "QPlainTextEdit { background: #ffffff; color: #24292f; "
        "border: 1px solid #d0d7de; padding: 4px; }"
    ),
    "pcb": (
        "QPlainTextEdit { background: #0a3322; color: #f0e6c8; "
        "border: 1px solid #1c7a52; padding: 4px; }"
    ),
}
_THEME_GUTTER_BG = {"dark": "#1a1a28", "light": "#f6f8fa", "pcb": "#0e3d2b"}
_THEME_GUTTER_FG = {"dark": "#585b70", "light": "#8c959f", "pcb": "#8fbf9f"}
_active_theme = "dark"


def _format_for(token) -> QTextCharFormat:
    fmt = QTextCharFormat()
    cur = token
    while cur is not None:
        key = str(cur)
        if key in _PALETTE:
            fmt.setForeground(QColor(_PALETTE[key]))
            break
        cur = getattr(cur, "parent", None)
    return fmt


def apply_theme(name: str) -> None:
    """Update module-level palette so all new highlights use the new theme."""
    global _PALETTE, _active_theme
    _active_theme = name if name in ("dark", "light", "pcb") else "dark"
    _PALETTE.clear()
    if _active_theme == "light":
        _PALETTE.update(_PALETTE_LIGHT)
    elif _active_theme == "pcb":
        # Reuse dark palette for tokens — background is dark green so contrast works.
        _PALETTE.update(_PALETTE_DARK)
    else:
        _PALETTE.update(_PALETTE_DARK)


class _PygmentsHighlighter(QSyntaxHighlighter):
    def __init__(self, doc: QTextDocument, language: str) -> None:
        super().__init__(doc)
        self._language = language
        self._lexer = None
        if lex is not None:
            if language == "verilog" and VerilogLexer is not None:
                self._lexer = VerilogLexer()
            elif language == "spice" and SpiceLexer is not None:
                self._lexer = SpiceLexer()

    def highlightBlock(self, text: str) -> None:  # noqa: D401
        if not text:
            return
        if self._lexer is not None and lex is not None:
            offset = 0
            for token, value in lex(text, self._lexer):
                length = len(value)
                if length:
                    self.setFormat(offset, length, _format_for(token))
                offset += length
            return
        # Fallback: highlight comments and numbers heuristically
        if self._language == "verilog":
            self._fallback_verilog(text)
        elif self._language == "spice":
            self._fallback_spice(text)

    def _fallback_verilog(self, text: str) -> None:
        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6c7086"))
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#cba6f7"))
        idx = text.find("//")
        if idx >= 0:
            self.setFormat(idx, len(text) - idx, comment_fmt)
        for kw in ("module", "endmodule", "input", "output", "wire", "reg",
                   "always", "assign", "begin", "end", "if", "else", "case",
                   "endcase", "posedge", "negedge"):
            start = 0
            while True:
                i = text.find(kw, start)
                if i < 0:
                    break
                self.setFormat(i, len(kw), kw_fmt)
                start = i + len(kw)

    def _fallback_spice(self, text: str) -> None:
        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6c7086"))
        directive_fmt = QTextCharFormat()
        directive_fmt.setForeground(QColor("#cba6f7"))
        if text.startswith("*"):
            self.setFormat(0, len(text), comment_fmt)
            return
        if text.startswith("."):
            end = text.find(" ")
            self.setFormat(0, end if end > 0 else len(text), directive_fmt)


# ---------------------------------------------------------------------------
# Editor with line-number gutter
# ---------------------------------------------------------------------------
class _LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: D401
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: D401
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, language: str = "verilog", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(10)
        self.setFont(font)
        self.setTabChangesFocus(True)
        self.setStyleSheet(_THEME_EDITOR_STYLE[_active_theme])
        self._language = language
        self._highlighter = _PygmentsHighlighter(self.document(), language)
        self._gutter = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._on_update_request)
        self._update_gutter_width()

    # -- public API ------------------------------------------------------
    def set_code(self, code: str) -> None:
        self.setPlainText(code or "")

    def set_language(self, language: str) -> None:
        self._language = language
        self._highlighter.setDocument(None)
        self._highlighter = _PygmentsHighlighter(self.document(), language)

    def apply_theme(self, name: str) -> None:
        """Update widget colours + re-highlight for the given theme name."""
        apply_theme(name)  # update module-level palette
        self.setStyleSheet(_THEME_EDITOR_STYLE.get(name, _THEME_EDITOR_STYLE["dark"]))
        self._gutter.update()
        # Re-run highlighting so token colours are refreshed.
        self._highlighter.rehighlight()

    # -- gutter ----------------------------------------------------------
    def line_number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 18 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: D401
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(),
                                       self.line_number_width(), cr.height()))

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(_THEME_GUTTER_BG.get(_active_theme, "#1a1a28")))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        painter.setPen(QColor(_THEME_GUTTER_FG.get(_active_theme, "#585b70")))
        painter.setFont(self.font())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, self._gutter.width() - 6,
                                 self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(block_number + 1))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
