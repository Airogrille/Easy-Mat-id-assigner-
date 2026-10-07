from PySide6 import QtCore, QtGui, QtWidgets
from pymxs import runtime as rt
import qtmax

from . import core

_CALLBACK_ID = rt.Name("EasyMatID")
_EVENTS = (
    "selectionSetChanged", "modPanelObjPostChange", "sceneUndo", "sceneRedo",
    "filePostOpen", "systemPostNew", "systemPostReset",
)
_panel = None


def _swatch(rgb):
    pix = QtGui.QPixmap(16, 16)
    pix.fill(QtGui.QColor(*rgb) if rgb else QtGui.QColor(90, 90, 90))
    return QtGui.QIcon(pix)


class Panel(QtWidgets.QDockWidget):
    def __init__(self, parent):
        super().__init__("Easy Mat ID", parent)
        self.setObjectName("EasyMatIDDock")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        body = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(body)
        self.obj_label = QtWidgets.QLabel()
        self.mat_label = QtWidgets.QLabel()
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.list.itemClicked.connect(self._assign)
        self.add_btn = QtWidgets.QPushButton("Add material")
        self.add_btn.clicked.connect(self._add)
        self.val_btn = QtWidgets.QPushButton("Validate")
        self.val_btn.clicked.connect(self._validate)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.val_btn)
        for w in (self.obj_label, self.mat_label, self.list):
            lay.addWidget(w)
        lay.addLayout(buttons)
        lay.addWidget(self.status)
        self.setWidget(body)

        # Selection events come in bursts; refresh once per burst.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        for event in _EVENTS:
            rt.callbacks.addScript(rt.Name(event), self._schedule, id=_CALLBACK_ID)
        self.refresh()

    def _schedule(self, *_):
        self._timer.start(0)

    def closeEvent(self, event):
        rt.callbacks.removeScripts(id=_CALLBACK_ID)
        super().closeEvent(event)

    def refresh(self):
        self.list.clear()
        self.status.clear()
        node = core.current_node()
        ok = node is not None and core.is_editable(node)
        self.add_btn.setEnabled(ok)
        self.val_btn.setEnabled(ok)
        if node is None:
            self.obj_label.setText("Select one object")
            self.mat_label.clear()
            return
        self.obj_label.setText("Object: %s" % node.name)
        if not ok:
            self.mat_label.setText("Needs Editable Poly or Edit Poly")
            return
        mat_name, slots = core.read_slots(node)
        self.mat_label.setText("Material: %s" % (mat_name or "none"))
        for s in slots:
            item = QtWidgets.QListWidgetItem(_swatch(s.rgb), "%2d   %s" % (s.id, s.name or "<empty>"))
            item.setData(QtCore.Qt.UserRole, s.id)
            self.list.addItem(item)

    def _assign(self, item):
        node = core.current_node()
        if node is None:
            return
        count = core.assign(node, item.data(QtCore.Qt.UserRole))
        self.status.setText("%s -> %d faces" % (item.text().split(None, 1)[-1], count))

    def _add(self):
        node = core.current_node()
        if node is None:
            return
        name, count = core.add_material(node)
        self.refresh()
        self.status.setText("%s -> %d faces" % (name, count))

    def _validate(self):
        node = core.current_node()
        if node is None:
            return
        issues = core.validate(node)
        self.status.setText("\n".join(issues) if issues else "OK: ready for export.")


def show():
    global _panel
    if _panel is not None:
        try:
            _panel.close()
        except RuntimeError:  # Qt object already deleted
            pass
    main = qtmax.GetQMaxMainWindow()
    _panel = Panel(main)
    main.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
    _panel.setFloating(True)
    _panel.show()
