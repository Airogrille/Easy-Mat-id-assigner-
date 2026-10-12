import time

from PySide6 import QtCore, QtGui, QtWidgets
from pymxs import runtime as rt
import qtmax
from shiboken6 import isValid

from . import core

_CALLBACK_ID = rt.Name("EasyMatID")
_EVENTS = (
    "selectionSetChanged", "modPanelObjPostChange", "sceneUndo", "sceneRedo",
    "nodePostMaterial", "filePostOpen", "systemPostNew", "systemPostReset",
)
_panel = None


def _label(text=""):
    label = QtWidgets.QLabel(text)
    label.setTextFormat(QtCore.Qt.PlainText)
    return label


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().deleteLater()


class SlotRow(QtWidgets.QWidget):
    assign_requested = QtCore.Signal(int)
    select_requested = QtCore.Signal(int)
    remove_requested = QtCore.Signal(int)
    error = QtCore.Signal(str)

    def __init__(self, slot, only_slot, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.setToolTip("Click: assign to selected polygons · Shift+Click: whole object · Right-click: select polygons")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.swatch = _label()
        self.swatch.setFixedSize(14, 14)
        pixmap = QtGui.QPixmap(14, 14)
        pixmap.fill(QtGui.QColor(*(slot.rgb if slot.rgb is not None else (90, 90, 90))))
        self.swatch.setPixmap(pixmap)
        self.id_label = _label(str(slot.id))
        self.name_label = _label(slot.name if slot.name is not None else "<empty>")
        for label in (self.swatch, self.id_label, self.name_label):
            label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        layout.setStretch(2, 1)
        if slot.kind is None:
            for label in (self.id_label, self.name_label):
                font = label.font()
                font.setItalic(True)
                label.setFont(font)

        self.remove_btn = None
        if slot.kind != "blank":
            self.remove_btn = QtWidgets.QToolButton(self)
            self.remove_btn.setText("×")
            self.remove_btn.setEnabled(not only_slot)
            self.remove_btn.setToolTip(
                "The only slot — add another color first" if only_slot
                else "Remove slot, its polygons go to Blank"
            )
            self.remove_btn.clicked.connect(self._remove)
            layout.addWidget(self.remove_btn)
            self.remove_btn.hide()

    def _remove(self):
        try:
            self.remove_requested.emit(self.slot.index)
        except Exception as exc:
            self.error.emit(str(exc))

    def mousePressEvent(self, event):
        try:
            if event.button() == QtCore.Qt.LeftButton:
                event.accept()
                self.assign_requested.emit(self.slot.id)
            elif event.button() == QtCore.Qt.RightButton:
                event.accept()
                self.select_requested.emit(self.slot.id)
            else:
                super().mousePressEvent(event)
        except Exception as exc:
            self.error.emit(str(exc))

    def enterEvent(self, event):
        try:
            if self.remove_btn is not None:
                self.remove_btn.show()
            super().enterEvent(event)
        except Exception as exc:
            self.error.emit(str(exc))

    def leaveEvent(self, event):
        try:
            if self.remove_btn is not None:
                self.remove_btn.hide()
            super().leaveEvent(event)
        except Exception as exc:
            self.error.emit(str(exc))


class Panel(QtWidgets.QDockWidget):
    def __init__(self, parent):
        super().__init__("Easy Mat ID", parent)
        self.setObjectName("EasyMatIDDock")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.setMinimumWidth(280)
        self._node_handle = None
        self._closed = False
        self._refresh_pending = False
        self._selected_pending = False
        self.rows = []
        self.issue_buttons = []

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        self.obj_label = _label()
        self.mat_label = _label()
        layout.addWidget(self.obj_label)
        layout.addWidget(self.mat_label)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        slots = QtWidgets.QWidget()
        self.slot_layout = QtWidgets.QVBoxLayout(slots)
        self.slot_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(slots)
        layout.addWidget(self.scroll, 1)
        self.selected_label = _label()
        layout.addWidget(self.selected_label)

        self.add_btn = QtWidgets.QPushButton("Add material")
        self.add_btn.setToolTip("Add next color to selected polygons · Shift: whole object")
        self.add_btn.clicked.connect(self._add)
        self.val_btn = QtWidgets.QPushButton("Validate")
        self.val_btn.clicked.connect(self._validate)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.val_btn)
        layout.addLayout(buttons)

        self.validation = QtWidgets.QWidget()
        self.validation_layout = QtWidgets.QVBoxLayout(self.validation)
        self.validation_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.validation)
        self.status = _label()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setWidget(body)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush_updates)
        self.destroyed.connect(lambda *_: _panel_destroyed(self))
        try:
            for event in _EVENTS:
                rt.callbacks.addScript(rt.Name(event), self._schedule_refresh, id=_CALLBACK_ID)
            rt.callbacks.addScript(rt.Name("preSystemShutdown"), teardown, id=_CALLBACK_ID)
            rt.emid_installEvents()
        except Exception as exc:
            self._stop_updates()
            teardown()
            self._show_error(str(exc))
            return
        self.refresh()

    def _resume_updates(self):
        try:
            if self._closed or not isValid(self) or bool(rt.emid_busy):
                return
            if (self._refresh_pending or self._selected_pending) and not self._timer.isActive():
                self._timer.start(0)
        except Exception as exc:
            self._show_error(str(exc))

    def _queue_update(self, full):
        if self._closed or not isValid(self) or bool(rt.emid_busy):
            return
        if full:
            self._refresh_pending = True
            self._selected_pending = False
        elif not self._refresh_pending:
            self._selected_pending = True
        self._resume_updates()

    def _schedule_refresh(self, *_):
        try:
            self._queue_update(True)
        except Exception as exc:
            self._show_error(str(exc))

    def _schedule_selected(self, *_):
        try:
            self._queue_update(False)
        except Exception as exc:
            self._show_error(str(exc))

    def _flush_updates(self):
        try:
            if self._closed or not isValid(self) or bool(rt.emid_busy):
                return
            full, selected = self._refresh_pending, self._selected_pending
            self._refresh_pending = self._selected_pending = False
            if full:
                self.refresh()
            elif selected:
                self._update_selected(core.current_node())
        except Exception as exc:
            self._show_error(str(exc))

    def _stop_updates(self):
        self._closed = True
        self._refresh_pending = self._selected_pending = False
        if isValid(self):
            self._timer.stop()

    def closeEvent(self, event):
        try:
            if _panel is self:
                teardown()
            else:
                self._stop_updates()
            super().closeEvent(event)
        except Exception as exc:
            self._show_error(str(exc))
            event.accept()

    def _set_status(self, text, ok=True, ms=None):
        if ms is not None:
            text += "  (%.0f ms)" % ms
        self.status.setText(text)
        self.status.setStyleSheet("" if ok else "color: orange;")

    def _show_error(self, text):
        try:
            self._set_status("Error: " + text, False)
        except RuntimeError:  # A late event can belong to an already deleted dock.
            pass

    def _clear_validation(self):
        _clear_layout(self.validation_layout)
        self.issue_buttons = []
        self.validation.hide()

    def _update_selected(self, node):
        selected = core.read_selected_ids(node)
        self.selected_label.setVisible(selected is not None)
        if selected is not None:
            ids, truncated = selected
            text = "Selected: ID " + ", ".join(str(mat_id) for mat_id in ids)
            self.selected_label.setText(text + (" +…" if truncated else ""))

    def refresh(self):
        try:
            if self._closed or not isValid(self):
                return False
            # An explicit full refresh also satisfies any already queued requests.
            self._timer.stop()
            self._refresh_pending = self._selected_pending = False
            node = core.current_node()
            state = core.read_state(node)
            handle = None if node is None else int(rt.getHandleByAnim(node))
            if handle != self._node_handle:
                self._clear_validation()
                self.status.clear()
                self._node_handle = handle
            enabled = node is not None and state.editable
            self.add_btn.setEnabled(enabled)
            self.val_btn.setEnabled(enabled)
            self.obj_label.setText("Select one object" if node is None else "Object: " + state.node_name)
            self.mat_label.setText("Material: " + (state.material_name or "none"))
            _clear_layout(self.slot_layout)
            self.rows = []
            for slot in state.slots:
                row = SlotRow(slot, len(state.slots) == 1)
                row.setEnabled(enabled)
                row.assign_requested.connect(self._assign)
                row.select_requested.connect(self._select_id)
                row.remove_requested.connect(self._remove)
                row.error.connect(self._show_error)
                self.slot_layout.addWidget(row)
                self.rows.append(row)
            self.slot_layout.addStretch()
            self._update_selected(node)
            if node is None:
                self._set_status("Select one object", False)
            elif not state.editable:
                self._set_status("Needs Editable Poly or Edit Poly", False)
            return True
        except Exception as exc:
            self._show_error(str(exc))
            return False

    @staticmethod
    def _whole():
        return bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier)

    def _perform(self, operation):
        try:
            node = core.current_node()
            self._clear_validation()
            if node is None or not core.read_state(node).editable:
                self.refresh()
                return
            result = operation(node)
            if self.refresh() is False:
                return
            self._set_status(result.text, result.ok, result.ms)
        except Exception as exc:
            self._show_error(str(exc))
        finally:
            self._resume_updates()

    def _assign(self, mat_id):
        self._perform(lambda node: core.assign(node, mat_id, self._whole()))

    def _select_id(self, mat_id):
        self._perform(lambda node: core.select_id(node, mat_id))

    def _remove(self, index):
        self._perform(lambda node: core.remove(node, index))

    def _add(self):
        self._perform(lambda node: core.add(node, self._whole()))

    def _issue_action(self, action):
        self._perform(core.select_unslotted if action == "select_unslotted" else core.clean)

    def _validate(self):
        try:
            node = core.current_node()
            if node is None or not core.read_state(node).editable:
                self.refresh()
                return
            self._clear_validation()
            started = time.perf_counter()
            issues = core.validate(node)
            elapsed = (time.perf_counter() - started) * 1000
            for issue in issues:
                row = QtWidgets.QWidget()
                layout = QtWidgets.QHBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 0)
                text = _label(issue.text)
                text.setWordWrap(True)
                layout.addWidget(text, 1)
                if issue.action:
                    button = QtWidgets.QToolButton()
                    button.setText("Select" if issue.action == "select_unslotted" else "Clean")
                    button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
                    button.clicked.connect(lambda checked=False, action=issue.action: self._issue_action(action))
                    layout.addWidget(button)
                    self.issue_buttons.append(button)
                self.validation_layout.addWidget(row)
            self.validation.setVisible(bool(issues))
            text = "1 issue." if len(issues) == 1 else "%d issues." % len(issues)
            self._set_status(text if issues else "OK: ready for export.", not issues, elapsed)
        except Exception as exc:
            self._show_error(str(exc))
        finally:
            self._resume_updates()


def on_subsel():
    panel = _panel
    if panel is not None and isValid(panel) and not panel._closed:
        panel._schedule_selected()


def teardown(*_):
    global _panel
    panel, _panel = _panel, None
    try:
        try:
            if panel is not None:
                panel._closed = True
                panel._refresh_pending = panel._selected_pending = False
                if isValid(panel):
                    panel._timer.stop()
        finally:
            try:
                rt.callbacks.removeScripts(id=_CALLBACK_ID)
            finally:
                rt.emid_teardownEvents()
    except Exception as exc:
        if panel is not None and isValid(panel):
            panel._show_error(str(exc))


def _panel_destroyed(panel):
    # Deleting an old dock must not remove a newer dock's subscriptions.
    if _panel is panel:
        teardown()


def show():
    global _panel
    previous = _panel
    teardown()
    if previous is not None and isValid(previous):
        try:
            previous.close()
        except RuntimeError:  # Qt object already deleted
            pass
    main = qtmax.GetQMaxMainWindow()
    _panel = Panel(main)
    main.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
    _panel.show()
