"""Python API for EasyMatID; polygon and material changes run in emid_core.ms."""
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path
import time

import pymxs
from pymxs import runtime as rt

from . import naming

Slot = namedtuple("Slot", "index id name rgb kind cls")
State = namedtuple("State", "node_name editable material_name is_multi slots")
Issue = namedtuple("Issue", "text action")
Result = namedtuple("Result", "ok text ms")

rt.fileIn(str(Path(__file__).with_name("emid_core.ms")))


def current_node():
    return rt.selection[0] if rt.selection.count == 1 else None


def read_state(node):
    """Read the material and editability without querying mesh faces."""
    if node is None:
        return State(None, False, None, False, [])
    editable = rt.emid_target(node) is not None
    material = node.material
    if material is None:
        return State(str(node.name), editable, None, False, [])
    if rt.classOf(material) != rt.Multimaterial:
        return State(str(node.name), editable, str(material.name), False, [])
    slots = []
    for index, (mat_id, sub) in enumerate(
        zip(material.materialIDList, material.materialList), start=1
    ):
        rgb = None
        if sub is not None and rt.classOf(sub) == rt.Standardmaterial:
            color = sub.diffuse
            rgb = (int(color.r), int(color.g), int(color.b))
        kind = rt.emid_kind(sub)
        slots.append(Slot(
            index, int(mat_id), None if sub is None else str(sub.name), rgb,
            None if kind is None else str(kind), str(rt.classOf(sub)),
        ))
    return State(str(node.name), editable, str(material.name), True, slots)


def read_selected_ids(node):
    if node is None:
        return None
    value = rt.emid_readSelectedIDs(node)
    if value is None:
        return None
    return [int(mat_id) for mat_id in value[0]], bool(value[1])


@contextmanager
def _action(label):
    t0 = time.perf_counter()
    elapsed = [0.0]
    error = None
    rt.emid_busy = True
    try:
        with pymxs.undo(True, "EasyMatID: " + label):
            try:
                yield elapsed
            except Exception as exc:
                # Let pymxs roll back first; its context suppresses the exception.
                error = exc
                raise
        if error is not None:
            raise error
    finally:
        rt.emid_busy = False
        rt.redrawViews()
        elapsed[0] = (time.perf_counter() - t0) * 1000


@contextmanager
def _quiet():
    rt.emid_busy = True
    try:
        with pymxs.undo(False):
            yield
    finally:
        rt.emid_busy = False


def _run_action(label, operation, success_text, rejection="Select polygons (Shift = whole object)"):
    with _action(label) as elapsed:
        count = int(operation())
    if count == -1:
        return Result(False, rejection, elapsed[0])
    if count == -2:
        return Result(False, "The only slot can't be removed", elapsed[0])
    return Result(True, success_text(count), elapsed[0])


def add(node, whole):
    state = read_state(node)
    label, rgb = naming.next_color(
        naming.color_of(slot.name)
        for slot in state.slots if slot.kind == "slot" and slot.name
    )
    name = naming.material_name(str(node.name), label)
    blank_name = naming.material_name(str(node.name), naming.BLANK)
    return _run_action(
        "add material",
        lambda: rt.emid_actAdd(
            node, name, rt.color(*rgb), blank_name, rt.color(*naming.BLANK_RGB), whole
        ),
        lambda count: "%s -> %d faces" % (name, count),
    )


def assign(node, mat_id, whole):
    name = next(
        (slot.name for slot in read_state(node).slots if slot.id == mat_id and slot.name),
        "ID %d" % mat_id,
    )
    return _run_action(
        "assign ID", lambda: rt.emid_actAssign(node, mat_id, whole),
        lambda count: "%s -> %d faces" % (name, count),
    )


def remove(node, slot_index):
    name = next(
        (slot.name for slot in read_state(node).slots if slot.index == slot_index and slot.name),
        "slot %d" % slot_index,
    )
    blank_name = naming.material_name(str(node.name), naming.BLANK)
    return _run_action(
        "remove material",
        lambda: rt.emid_actRemove(node, slot_index, blank_name, rt.color(*naming.BLANK_RGB)),
        lambda count: "Removed %s, %d faces -> Blank" % (name, count),
        "Needs Editable Poly or Edit Poly",
    )


def select_id(node, mat_id):
    return _run_action(
        "select ID", lambda: rt.emid_actSelectID(node, mat_id),
        lambda count: "Selected ID %d -> %d faces" % (mat_id, count),
        "Needs Editable Poly or Edit Poly",
    )


def select_unslotted(node):
    return _run_action(
        "select unslotted", lambda: rt.emid_actSelectUnslotted(node),
        lambda count: "Selected %d faces without a material slot" % count,
        "Needs Editable Poly or Edit Poly",
    )


def clean(node):
    return _run_action(
        "clean", lambda: rt.emid_actClean(node),
        lambda count: "Cleaned %d empty slots" % count,
    )


def validate(node):
    """Explicit export diagnostics; preserve selection and leave Undo untouched."""
    with _quiet():
        state = read_state(node)
        if not state.is_multi:
            return [Issue("Material is not Multi/Sub-Object.", None)]

        issues = []
        face_issues = rt.emid_readFaceIssues(node)
        if face_issues is not None:
            unslotted, empty = face_issues
            if unslotted:
                issues.append(Issue(
                    "%d faces have no material slot — Unity can't assign a material to them." % unslotted,
                    "select_unslotted",
                ))
            if len(empty):
                issues.append(Issue(
                    "Empty slots: ID %s." % ", ".join(str(int(mat_id)) for mat_id in empty),
                    "clean",
                ))

        names = {}
        for slot, sub in zip(state.slots, node.material.materialList):
            if sub is None:
                issues.append(Issue("ID %d: empty slot." % slot.id, None))
                continue
            cls = rt.classOf(sub)
            if cls == rt.Multimaterial:
                issues.append(Issue("ID %d: nested Multi/Sub — Unity can't use it." % slot.id, None))
            elif cls != rt.Standardmaterial:
                issues.append(Issue("ID %d: %s, use Standard." % (slot.id, slot.cls), None))
            if not naming.VALID_NAME.match(slot.name):
                issues.append(Issue("ID %d: '%s' breaks MT_ naming." % (slot.id, slot.name), None))
            names.setdefault(slot.name, []).append(slot.id)

        for name in sorted(names):
            if len(names[name]) > 1:
                issues.append(Issue("'%s' is used by several slots." % name, None))

        # A shared handle is one material, however many objects reference it.
        handles = {}
        for obj in rt.objects:
            material = obj.material
            if material is None:
                continue
            subs = material.materialList if rt.classOf(material) == rt.Multimaterial else [material]
            for sub in subs:
                if sub is not None:
                    handles.setdefault(str(sub.name), set()).add(int(rt.getHandleByAnim(sub)))
        for name in sorted(names):
            if len(handles.get(name, ())) > 1:
                issues.append(Issue("'%s': another material in the scene has the same name." % name, None))
        return issues
