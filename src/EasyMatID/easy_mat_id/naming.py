"""Material names. Pure Python: no 3ds Max imports, testable outside Max.

Scheme (SpiderRig asset-naming.md): SM_Factory_Pipe_A -> MT_Factory_Pipe_A_Red
"""
import re

MESH_PREFIXES = ("SM_", "RM_", "SK_")
MATERIAL_PREFIX = "MT_"
VALID_NAME = re.compile(r"^MT_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*$")
BLANK = "Blank"
BLANK_RGB = (160, 160, 160)

# Order = order of "Add material". Colors are picked to stay distinct in the viewport.
COLORS = (
    ("Red", (220, 50, 47)),
    ("Yellow", (240, 200, 30)),
    ("Green", (60, 170, 60)),
    ("Blue", (40, 100, 220)),
    ("Orange", (245, 130, 30)),
    ("Purple", (140, 70, 190)),
    ("Cyan", (30, 190, 200)),
    ("Magenta", (220, 60, 170)),
    ("Lime", (160, 220, 40)),
    ("Brown", (140, 90, 50)),
    ("Pink", (250, 150, 180)),
    ("Teal", (0, 128, 128)),
    ("Navy", (30, 40, 120)),
    ("Olive", (128, 128, 0)),
    ("White", (235, 235, 235)),
    ("Black", (30, 30, 30)),
)


def base_name(node_name):
    """Mesh name without the mesh prefix, reduced to [A-Za-z0-9_]."""
    name = node_name
    for prefix in MESH_PREFIXES:
        if name.upper().startswith(prefix):
            name = name[len(prefix):]
            break
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return name or "Mesh"


def material_name(node_name, color):
    return "%s%s_%s" % (MATERIAL_PREFIX, base_name(node_name), color)


def color_of(material_name):
    """Color label = last block of the name: MT_Pipe_A_Red -> Red."""
    return material_name.rsplit("_", 1)[-1]


def next_color(used_labels):
    """First free palette color. After a full cycle: Red2, Yellow2, ..."""
    used = set(used_labels)
    cycle = 1
    while True:
        for color, rgb in COLORS:
            label = color if cycle == 1 else "%s%d" % (color, cycle)
            if label not in used:
                return label, rgb
        cycle += 1
