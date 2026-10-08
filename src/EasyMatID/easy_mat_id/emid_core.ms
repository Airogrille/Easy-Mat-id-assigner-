-- EasyMatID core: polygon and material operations. Loaded once by core.py.
-- Rules: no loops over all faces; per-slot work goes through native select-by-material.
global EMID_TAG = 0x454D4944      -- appData channel on our materials: "slot" | "blank"
global emid_busy = false          -- set by Python while an action runs; events are ignored
global emid_nec = undefined       -- NodeEventCallback for sub-object selection

fn emid_current = if getCommandPanelTaskMode() == #modify then modPanel.getCurrentObject() else undefined

-- Edit_Poly modifier, #poly (Editable Poly base object) or undefined
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

fn emid_isCurrent t = (
    local c = emid_current()
    if t == #poly then classOf c == Editable_Poly else c == t
)

-- true when the user works with polygons of this target right now
fn emid_atPolyLevel t = emid_isCurrent t and (subObjectLevel == 4 or subObjectLevel == 5)

fn emid_numFaces n t = if t == #poly then polyop.getNumFaces n else t.GetNumFaces node:n
fn emid_allFaces n t = (local k = emid_numFaces n t; if k == 0 then #{} else #{1..k})
fn emid_getSel n t = if t == #poly then polyop.getFaceSelection n else t.GetSelection #Face node:n
-- Edit Poly: SetSelection is dead from script; Select works (check_contexts v4-v5)
fn emid_setSel n t ba = (
    if t == #poly then polyop.setFaceSelection n ba
    else (
        t.Select #Face (emid_allFaces n t) select:false node:n
        t.Select #Face ba node:n
    )
)

-- Edit Poly works only while it is current in the stack: make it current. Returns target or undefined.
fn emid_ready n = (
    local t = emid_target n
    if t != undefined and t != #poly and not emid_isCurrent t do (
        max modify mode
        modPanel.setCurrentObject t
    )
    t
)

-- Leaves the union of faces with these IDs selected and returns it. Caller restores selection.
fn emid_selectIDs n t ids = (
    if ids.count == 0 do (emid_setSel n t #{}; return #{})
    if t == #poly then (
        for k = 1 to ids.count do n.selectByMaterial ids[k] clearCurrentSelection:(k == 1)
        polyop.getFaceSelection n
    ) else (
        local lvl = t.GetEPolySelLevel()
        t.SetEPolySelLevel #Face
        for k = 1 to ids.count do (
            t.selectByMaterialID = ids[k] - 1  -- 0-based
            t.selectByMaterialClear = (k == 1)
            t.ButtonOp #SelectByMaterial
        )
        local r = t.GetSelection #Face node:n
        t.SetEPolySelLevel lvl
        r
    )
)

fn emid_facesOfIDs n t ids = (
    local saved = emid_getSel n t
    local r = emid_selectIDs n t ids
    emid_setSel n t saved
    r
)

-- subset of ids that still have at least one face
fn emid_usedIDs n t ids = (
    local saved = emid_getSel n t
    local used = for id in ids where not (emid_selectIDs n t #(id)).isEmpty collect id
    emid_setSel n t saved
    used
)

fn emid_setID n t faces id = (
    if t == #poly then polyop.setFaceMatID n faces id
    else (
        local saved = t.GetSelection #Face node:n
        local lvl = t.GetEPolySelLevel()
        t.SetEPolySelLevel #Face
        emid_setSel n t faces
        t.SetOperation #SetMaterial
        t.materialIDToSet = id - 1             -- 0-based
        t.Commit()
        emid_setSel n t saved                  -- safe right after Commit (check_contexts v5)
        t.SetEPolySelLevel lvl
    )
)

-- faces an action applies to: whole object, the polygon selection, or undefined (= do nothing)
fn emid_targetFaces n t whole = (
    if whole then emid_allFaces n t
    else if not emid_atPolyLevel t then undefined
    else (local s = emid_getSel n t; if s.isEmpty then undefined else s)
)

-- ---------- materials ----------
fn emid_kind m = if m == undefined then undefined else getAppData m EMID_TAG
fn emid_newMat nm clr kind = (
    local m = Standardmaterial name:nm diffuse:clr
    setAppData m EMID_TAG kind
    m
)
fn emid_nextID mm = (local id = 0; for i in mm.materialIDList where i > id do id = i; id + 1)

fn emid_appendSlot mm m id = (
    local i = mm.materialList.count + 1     -- reading numsubs is NOT the slot count
    mm.numsubs = i                          -- writing numsubs resizes the slot list
    mm.materialList[i] = m
    mm.materialIDList[i] = id
    mm.names[i] = m.name
)

-- drops slots by 1-based index; never leaves the Multi empty
fn emid_removeSlots mm idxs = (
    local keep = for i = 1 to mm.materialList.count where findItem idxs i == 0 collect i
    if keep.count == 0 do return false
    local mats = for i in keep collect mm.materialList[i]
    local ids = for i in keep collect mm.materialIDList[i]
    local names = for i in keep collect mm.names[i]
    mm.numsubs = keep.count
    for k = 1 to keep.count do (
        mm.materialList[k] = mats[k]
        mm.materialIDList[k] = ids[k]
        if names[k] != undefined do mm.names[k] = names[k]
    )
    true
)

-- Never `n.material = m` directly: on Editable Poly open at Polygon level with selected faces
-- Max assigns the material TO THE SELECTION (new face ID, wraps into a new Multi).
-- check_isolate v2 M1/M2, 08.10.2026. Edit Poly and non-current nodes are not affected.
fn emid_assignMat n m = (
    local lvl = subObjectLevel
    local drop = lvl != undefined and lvl != 0
    if drop do subObjectLevel = 0
    try (n.material = m) catch (
        if drop do subObjectLevel = lvl       -- user's level comes back on error too
        throw()                               -- re-raise the original exception
    )
    if drop do subObjectLevel = lvl
)

-- A Multi shared by several nodes gets copied for this node before any change to it.
-- `copy` creates new sub-materials and drops their appData (check_isolate v1 S3c): re-tag by index.
fn emid_ownMulti n = (
    local m = n.material
    if classOf m == Multimaterial and (refs.dependentNodes m).count > 1 do (
        local c = copy m
        for i = 1 to m.materialList.count where m.materialList[i] != undefined and c.materialList[i] != undefined do (
            local k = getAppData m.materialList[i] EMID_TAG
            if k != undefined do setAppData c.materialList[i] EMID_TAG k
        )
        emid_assignMat n c
        m = c
    )
    m
)

-- Own Multi for this node: copy if shared; create Blank-only Multi (all faces -> Blank) if absent
fn emid_ensureMulti n t blankName blankClr = (
    local m = emid_ownMulti n
    if classOf m == Multimaterial then m
    else (
        local mm = Multimaterial numsubs:1
        mm.name = n.name + "_Multi"
        mm.materialList[1] = emid_newMat blankName blankClr "blank"
        mm.materialIDList[1] = 1
        mm.names[1] = blankName
        emid_assignMat n mm
        emid_setID n t (emid_allFaces n t) 1
        mm
    )
)

-- removes empty slots: ours only (onlyOurs:true) or all. Returns number removed.
fn emid_prune n t onlyOurs = (
    local mm = n.material
    if classOf mm != Multimaterial do return 0
    local idx = for i = 1 to mm.materialList.count where (not onlyOurs or emid_kind mm.materialList[i] != undefined) collect i
    if idx.count == 0 do return 0
    local ids = for i in idx collect mm.materialIDList[i]   -- not inline: "Bad free thunk" in Max 2027
    local used = emid_usedIDs n t ids
    local drop = for i in idx where findItem used mm.materialIDList[i] == 0 collect i
    if drop.count > 0 and emid_removeSlots mm drop then drop.count else 0
)

-- ---------- actions (called from Python inside one Undo record) ----------
-- Returns faces changed, or -1 when there is nothing to apply to.
fn emid_actAssign n id whole = (
    local t = emid_ready n
    if t == undefined do return -1
    local faces = emid_targetFaces n t whole
    if faces == undefined do return -1
    emid_ownMulti n                            -- prune below may change the Multi
    emid_setID n t faces id
    emid_prune n t true
    faces.numberSet
)

-- Returns faces changed, or -1 when there is nothing to apply to.
fn emid_actAdd n nm clr blankName blankClr whole = (
    local t = emid_ready n
    if t == undefined do return -1
    local faces = emid_targetFaces n t whole
    if faces == undefined do return -1
    local mm = emid_ensureMulti n t blankName blankClr
    local id = emid_nextID mm
    emid_appendSlot mm (emid_newMat nm clr "slot") id
    emid_setID n t faces id
    emid_prune n t true
    faces.numberSet
)

-- slotIndex: 1-based position in the Multi. Faces of the slot go to Blank (created if missing).
fn emid_actRemove n slotIndex blankName blankClr = (
    local t = emid_ready n
    if t == undefined or classOf n.material != Multimaterial do return -1
    local mm = emid_ownMulti n
    local id = mm.materialIDList[slotIndex]
    local faces = emid_facesOfIDs n t #(id)
    if not faces.isEmpty do (
        local bid = undefined
        for i = 1 to mm.materialList.count where emid_kind mm.materialList[i] == "blank" do bid = mm.materialIDList[i]
        if bid == undefined do (
            bid = if findItem (mm.materialIDList as array) 1 == 0 then 1 else emid_nextID mm
            emid_appendSlot mm (emid_newMat blankName blankClr "blank") bid
        )
        emid_setID n t faces bid
    )
    emid_removeSlots mm #(slotIndex)
    emid_prune n t true
    faces.numberSet
)

-- Selects faces of the ID and switches to Polygon level. Returns face count.
fn emid_actSelectID n id = (
    local t = emid_ready n
    if t == undefined do return -1
    max modify mode
    modPanel.setCurrentObject (if t == #poly then n.baseObject else t)
    subObjectLevel = 4
    (emid_selectIDs n t #(id)).numberSet
)

-- Selects faces whose ID has no slot, switches to Polygon level. Returns face count.
fn emid_actSelectUnslotted n = (
    local t = emid_ready n
    local mm = n.material
    if t == undefined or classOf mm != Multimaterial do return -1
    max modify mode
    modPanel.setCurrentObject (if t == #poly then n.baseObject else t)
    subObjectLevel = 4
    local faces = (emid_allFaces n t) - (emid_selectIDs n t (mm.materialIDList as array))
    emid_setSel n t faces
    faces.numberSet
)

fn emid_actClean n = (
    local t = emid_ready n
    if t == undefined do return -1
    emid_ownMulti n
    emid_prune n t false
)

-- ---------- reads ----------
-- #(ids, truncated) for the current polygon selection, or undefined when not at Polygon level
fn emid_readSelectedIDs n = (
    local t = emid_target n
    if t == undefined or not emid_atPolyLevel t do return undefined
    local s = emid_getSel n t
    local cap = if t == #poly then 20000 else 1000
    local b = #{}
    local k = 0
    for f in s while k < cap do (
        k += 1
        b[if t == #poly then polyop.getFaceMatID n f else t.GetFaceMaterial f node:n] = true
    )
    #(b as array, s.numberSet > cap)
)

-- #(faces without a slot, slot IDs without faces) for Validate
fn emid_readFaceIssues n = (
    local t = emid_ready n
    local mm = n.material
    if t == undefined or classOf mm != Multimaterial do return undefined
    local ids = mm.materialIDList as array
    local unslotted = (emid_allFaces n t) - (emid_facesOfIDs n t ids)
    local used = emid_usedIDs n t ids
    #(unslotted.numberSet, for id in ids where findItem used id == 0 collect id)
)

-- ---------- sub-object selection event ----------
fn emid_onSubSel ev nd = (
    if not emid_busy do python.Execute "import easy_mat_id.ui as _u; _u.on_subsel()"
)
fn emid_teardownEvents = (
    if emid_nec != undefined do (emid_nec.enabled = false; emid_nec = undefined)
    gc light:true
)
fn emid_installEvents = (
    emid_teardownEvents()
    emid_nec = NodeEventCallback mouseUp:true delay:100 subobjectSelectionChanged:emid_onSubSel
)
