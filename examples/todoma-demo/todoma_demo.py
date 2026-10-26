# TODOMA frame: GEOMETRY DEMONSTRATION, NOT AN AS-MEASURED TRAILER.
# All dimensions below are arbitrary placeholders in millimeters.
# This deliberately models an open folded channel, NOT a solid rectangular beam.
# Replace parameters and hole list with physical measurements before fabrication.
import math
from build123d import Box, Cylinder, Pos, Rot
from agentcad.api import show_object

# TEST-ONLY values; do NOT treat these as genuine TODOMA dimensions.
FRAME_HALF_WIDTH = 620.0
STRAIGHT_START_X = 950.0
STRAIGHT_END_X = 3100.0
WEB_HEIGHT = 85.0
FLANGE_WIDTH = 28.0
SHEET_THICKNESS = 3.0
NOSE_X = 0.0
NOSE_Y = 0.0
HOLE_X = [1250.0, 1490.0, 1850.0, 2190.0, 2650.0]
HOLE_DIAM = [18.0, 26.0, 18.0, 30.0, 18.0]

def open_channel(length, flange_direction, holes=None):
    # Local X axis follows the longitudinal rail, Y is web thickness.
    t = SHEET_THICKNESS
    h = WEB_HEIGHT
    w = FLANGE_WIDTH
    rail = Box(length, t, h)
    for z in (h / 2 - t / 2, -h / 2 + t / 2):
        flange = Pos(0, flange_direction * w / 2, z) * Box(length, w, t)
        rail = rail + flange
    for local_x, diameter in holes or []:
        # Through-hole perpendicular to upright web.
        tool = Pos(local_x, 0, 0) * Rot(90, 0, 0) * Cylinder(
            radius=diameter / 2, height=max(18, t * 6))
        rail = rail - tool
    return rail

length = STRAIGHT_END_X - STRAIGHT_START_X
center_x = (STRAIGHT_END_X + STRAIGHT_START_X) / 2
for side in (-1, 1):
    holes = [(x - center_x, diameter) for x, diameter in zip(HOLE_X, HOLE_DIAM)]
    longitudinal = Pos(center_x, side * FRAME_HALF_WIDTH, 0) * open_channel(
        length, -side, holes)
    show_object(longitudinal)

# A-shaped drawbar, represented by channel sections; real bends are not yet modeled.
for side in (-1, 1):
    dx = STRAIGHT_START_X - NOSE_X
    dy = side * FRAME_HALF_WIDTH - NOSE_Y
    diagonal_len = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx))
    diagonal = (
        Pos((NOSE_X + STRAIGHT_START_X) / 2, (NOSE_Y + side * FRAME_HALF_WIDTH) / 2, 0)
        * Rot(0, 0, angle)
        * open_channel(diagonal_len, -side, [])
    )
    show_object(diagonal)

# Crossmembers are independent components, retained for assembly-style edits.
for x in (1720.0, 2650.0):
    cross = Pos(x, 0, 0) * Box(55.0, 2 * FRAME_HALF_WIDTH - 2 * FLANGE_WIDTH, 45.0)
    show_object(cross)
