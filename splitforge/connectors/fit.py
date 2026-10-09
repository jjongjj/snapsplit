# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/fit.py
"""Does a connector stay inside the object?

A pin sticks out of its face by length/2 along the cut normal and the socket
reaches length/2 + clearance into the other side. On an oblique cut the walls
are slanted against that axis, so a connector whose seam point is well inside
the section can still break through the outer surface. These checks sample the
outer surface of the pin and socket solids (the same spans and sizes Build
uses) and test every sample against the source mesh.

Pure mathutils (BVHTree of the world-space source), no Blender data.
"""

import math

from mathutils import Vector

from . import shapes

RING_SAMPLES = 24
Z_SAMPLES = 9


def _outline(kind, width, height):
    """Cross-section outline points (local XY) of a CYL_PIN or RECT_TENON."""
    if kind == 'RECT_TENON':
        hw, hh = width * 0.5, height * 0.5
        pts = []
        for (x0, y0), (x1, y1) in (((-hw, -hh), (hw, -hh)), ((hw, -hh), (hw, hh)),
                                   ((hw, hh), (-hw, hh)), ((-hw, hh), (-hw, -hh))):
            pts += [(x0 + (x1 - x0) * k / 4.0, y0 + (y1 - y0) * k / 4.0) for k in range(4)]
        return pts
    r = width * 0.5
    return [(r * math.cos(2 * math.pi * k / RING_SAMPLES), r * math.sin(2 * math.pi * k / RING_SAMPLES))
            for k in range(RING_SAMPLES)]


def solid_samples(kind, width, height, z0, z1, matrix):
    """World points on the surface of a connector solid spanning z0..z1."""
    out = [matrix @ Vector((0.0, 0.0, z)) for z in (z0, z1)]
    outline = _outline(kind, width, height)
    for k in range(Z_SAMPLES):
        z = z0 + (z1 - z0) * k / (Z_SAMPLES - 1)
        out += [matrix @ Vector((x, y, z)) for x, y in outline]
    return out


def spec_samples(spec, pin_positive=None):
    """Surface samples of the pin and the socket of a ConnectorSpec."""
    side = spec.pin_positive if pin_positive is None else pin_positive
    pin, socket = shapes.pin_and_socket_spans(spec.length, spec.clearance, spec.gap, side)
    c2 = 2.0 * spec.clearance
    return (solid_samples(spec.kind, spec.width, spec.height, *pin, spec.matrix)
            + solid_samples(spec.kind, spec.width + c2, spec.height + c2, *socket, spec.matrix))


def depth_inside(bvh, point):
    """Distance of ``point`` inside the closed mesh (negative = outside)."""
    co, normal, _index, dist = bvh.find_nearest(point)
    if co is None:
        return -math.inf
    return dist if (point - co).dot(normal) < 0.0 else -dist


def worst_depth(bvh, spec, both_sides=False):
    """Smallest depth_inside over the connector's samples (negative: breaks through).

    ``both_sides`` also checks the mirrored pin side, so flipping pin_side later
    cannot break through either.
    """
    sides = (True, False) if both_sides else (spec.pin_positive,)
    return min(depth_inside(bvh, p) for side in sides for p in spec_samples(spec, side))
