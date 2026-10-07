"""Scene operations. Heavy work runs inside MAXScript helpers: one call per operation,
so a 100k-face mesh costs the same number of Python->Max round trips as a cube."""
from collections import namedtuple

import pymxs
from pymxs import runtime as rt

from . import naming

Slot = namedtuple("Slot", "id name rgb")

_MXS = r"""
fn emid_current = if getCommandPanelTaskMode() == #modify then modPanel.getCurrentObject() else undefined

-- What receives the IDs: Edit_Poly modifier, #poly (Editable Poly base object) or undefined.
fn emid_target n = (
    local c = emid_current()
    case of (
        (classOf c == Edit_Poly): c
        (classOf c == Editable_Poly): #poly
        (n.modifiers.count > 0 and classOf n.modifiers[1] == Edit_Poly): n.modifiers[1]
        (classOf n.baseObject == Editable_Poly): #poly
        default: undefined
    )
)

-- Sets ID on selected polygons, or on the whole object when nothing is selected
-- or the Polygon/Element level is not active. Returns the number of faces changed.
fn emid_assign n id all:false = (
    local t = emid_target n
    if t == undefined do return 0
    local c = emid_current()
    local isCur = if t == #poly then classOf c == Editable_Poly else c == t
    local useSel = not all and isCur and (subObjectLevel == 4 or subObjectLevel == 5)
    if t == #poly then (
        local faces = if useSel then polyop.getFaceSelection n else #{}
        if faces.isEmpty do faces = #{1..(polyop.getNumFaces n)}
        polyop.setFaceMatID n faces id
        faces.numberSet
    ) else (
        local sel = t.GetSelection #Face node:n
        local whole = not useSel or sel.isEmpty
        local lvl = t.GetEPolySelLevel()
        if whole do t.SetSelection #Face #{1..(t.GetNumFaces node:n)} node:n
        local count = (t.GetSelection #Face node:n).numberSet
        t.SetEPolySelLevel #Face
        t.SetOperation #SetMaterial
        t.materialIDToSet = id - 1  -- Edit Poly stores the ID 0-based
        t.Commit()
        t.SetEPolySelLevel lvl
        if whole do t.SetSelection #Face sel node:n
        count
    )
)

-- Appends a Standard material slot. A non-Multi material gets wrapped as slot 1;
-- a freshly created Multi first resets all faces to ID 1 so no face points past the slots.
fn emid_addSlot n mtlName clr = (
    local m = n.material
    local mm
    if classOf m == Multimaterial then (
        mm = m
        mm.numsubs += 1
    ) else (
        mm = Multimaterial numsubs:(if m == undefined then 1 else 2) name:(n.name + "_Multi")
        if m != undefined do (
            mm.materialList[1] = m
            mm.materialIDList[1] = 1
            mm.names[1] = m.name
        )
        n.material = mm
        emid_assign n 1 all:true
    )
    local i = mm.numsubs
    local id = 1
    for k = 1 to i - 1 do (if mm.materialIDList[k] >= id do id = mm.materialIDList[k] + 1)
    mm.materialList[i] = Standardmaterial name:mtlName diffuse:clr
    mm.materialIDList[i] = id
    mm.names[i] = mtlName
    id
)

fn emid_usedIDs n = (
    local m = n.mesh
    local b = #{}
    for f = 1 to m.numfaces do b[getFaceMatID m f] = true
    b as array
)
"""
rt.execute(_MXS)


def current_node():
    return rt.selection[0] if rt.selection.count == 1 else None


def is_editable(node):
    return rt.emid_target(node) is not None


def read_slots(node):
    """(material name or None, [Slot]) — Slot list is empty unless the material is Multi/Sub."""
    mat = node.material
    if mat is None:
        return None, []
    if rt.classOf(mat) != rt.Multimaterial:
        return str(mat.name), []
    slots = []
    for sid, sub in zip(mat.materialIDList, mat.materialList):
        if sub is None:
            slots.append(Slot(int(sid), None, None))
            continue
        rgb = None
        if rt.classOf(sub) == rt.Standardmaterial:
            c = sub.diffuse
            rgb = (int(c.r), int(c.g), int(c.b))
        slots.append(Slot(int(sid), str(sub.name), rgb))
    return str(mat.name), slots


def assign(node, mat_id):
    with pymxs.undo(True, "EasyMatID: assign ID"):
        count = rt.emid_assign(node, mat_id)
    rt.redrawViews()
    return count


def add_material(node):
    """Creates the next color slot and assigns it. Returns (name, faces changed)."""
    _, slots = read_slots(node)
    label, rgb = naming.next_color(naming.color_of(s.name) for s in slots if s.name)
    name = naming.material_name(str(node.name), label)
    with pymxs.undo(True, "EasyMatID: add material"):
        mat_id = rt.emid_addSlot(node, name, rt.color(*rgb))
        count = rt.emid_assign(node, mat_id)
    rt.redrawViews()
    return name, count


def validate(node):
    """Problems that break or confuse the Unity import. Empty list = clean."""
    mat = node.material
    if rt.classOf(mat) != rt.Multimaterial:
        return ["Material is not Multi/Sub-Object."]
    issues = []
    _, slots = read_slots(node)
    slot_ids = {s.id for s in slots}
    used = {int(i) for i in rt.emid_usedIDs(node)}

    for i in sorted(used - slot_ids):
        issues.append("ID %d: faces have no slot (Max wraps them onto another slot)." % i)
    for s in slots:
        if s.name is None:
            issues.append("ID %d: empty slot." % s.id)
        elif not naming.VALID_NAME.match(s.name):
            issues.append("ID %d: '%s' breaks the MT_ naming." % (s.id, s.name))
    for i in sorted(slot_ids - used):
        issues.append("ID %d: slot has no faces." % i)

    names = [s.name for s in slots if s.name]
    for n in sorted({n for n in names if names.count(n) > 1}):
        issues.append("'%s' is used by several slots." % n)

    # Different materials with one name merge into one material in Unity.
    handles = {}
    for obj in rt.objects:
        m = obj.material
        if m is None:
            continue
        subs = list(m.materialList) if rt.classOf(m) == rt.Multimaterial else [m]
        for sub in subs:
            if sub is not None:
                handles.setdefault(str(sub.name), set()).add(rt.getHandleByAnim(sub))
    for n in sorted(set(names)):
        if len(handles.get(n, ())) > 1:
            issues.append("'%s': another material in the scene has the same name." % n)
    return issues
