# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/shapes.py
"""Connector solids added straight into a bmesh (no objects, no mesh data-blocks).

Each shape is built in the connector's local frame: Z along the cut normal,
cross-section centered on the local origin, spanning ``z0 .. z1``. ``matrix``
maps that frame into the target bmesh's space (see placement.frame_matrix).
"""

import bmesh
from mathutils import Matrix

CYLINDER_SEGMENTS = 32


def add_solid(bm, kind, width, height, z0, z1, matrix, segments=CYLINDER_SEGMENTS):
    """Add a closed CYL_PIN (diameter ``width``) or RECT_TENON (``width`` x ``height``) solid."""
    lo, hi = min(z0, z1), max(z0, z1)
    center = matrix @ Matrix.Translation((0.0, 0.0, (lo + hi) * 0.5))
    if kind == 'CYL_PIN':
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                              radius1=width * 0.5, radius2=width * 0.5, depth=hi - lo, matrix=center)
    elif kind == 'RECT_TENON':
        scale = Matrix.Diagonal((width, height, hi - lo, 1.0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=center @ scale)
    else:
        raise ValueError(f"unsupported connector kind {kind!r}")


def pin_and_socket_spans(length, clearance, gap, pin_positive):
    """Local Z spans (pin, socket) of one connector.

    The seam plane is z = 0, the pin part's cut face at +gap/2 (pin_positive)
    or -gap/2. Half the pin is embedded in the pin part, the other half sticks
    out of its face. The socket starts behind the seam (so the boolean never
    meets a coplanar face) and reaches ``length/2 + clearance`` into the socket
    part, measured from its face: the depth after the gap is closed on assembly.
    """
    s = 1.0 if pin_positive else -1.0
    half_gap = max(gap, 0.0) * 0.5
    pin = (s * (half_gap - length * 0.5), s * (half_gap + length * 0.5))
    socket = (s * (half_gap + 0.1 * length), -s * (half_gap + length * 0.5 + clearance))
    return pin, socket
