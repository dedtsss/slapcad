"""
TODOMA PHOTO-BASED CONCEPT MODEL, 2026-10-29.
NOT DIMENSIONALLY MEASURED. ALL NUMBERS ARE EDITABLE GUESSES (MILLIMETRES).
No production drawing or verified strength. Photograph-based topology only.
The existing square crossmember is NOT a road axle.
Additional axle and leaf springs are purely a possible future configuration.
"""
import os
import math
from build123d import Box, Cylinder, Pos, Rot, Align
from agentcad.api import show_object

# Change these after the owner marks photo points and gives real values.
P = {
    "total_length": 3900.0,             # arbitrary preliminary
    "straight_half_width": 765.0,       # approximate outer rail half-span
    "channel_height": 100.0,
    "channel_flange": 30.0,
    "sheet_thickness": 3.0,
    "crossbar_x": 2200.0,               # EXISTING beam, never an axle
    "crossbar_section": 52.0,
    "new_axle_x": 2900.0,               # proposal only
    "new_axle_z": -230.0,
    "leaf_length": 900.0,
    "leaf_width": 52.0,
    "spring_arch": 45.0,
}
# Polyline point cloud in TOP view; two changes of direction approximate
# the Z/kinked transition into each straight longitudinal channel.
CENTERLINE = [(160,105), (840,315), (1090,485), (1510,765), (3900,765)]
MODIFIED = os.getenv("TODOMA_SUSPENSION","0")=="1"

H=P["channel_height"]; W=P["channel_flange"]; T=P["sheet_thickness"]

def local_channel(length, flange_sign):
    # C/U shaped folded sheet, open on the inside. No duplicate solid bar.
    web=Box(length,T,H)
    for z in (-H/2+T/2, H/2-T/2):
        web = web + Pos(0,flange_sign*(W/2-T/2),z)*Box(length,W,T)
    return web

def channel_segment(a,b,side,features):
    # Each run is a separate B-rep to preserve the geometric kinks at joints.
    dx=b[0]-a[0];dy=(b[1]-a[1])*side
    L=math.hypot(dx,dy)
    sign=-side
    beam=local_channel(L, sign)
    # All openings punched through the vertical web of this segment.
    for t,kind,dim in features:
        xx=(t-.5)*L
        if kind=="round":
            tool=Pos(xx,0,0)*Rot(90,0,0)*Cylinder(dim/2,50)
        elif kind=="slot":
            diam, overall_len=dim
            travel=max(0.,overall_len-diam)
            tool=Pos(xx-travel/2,0,0)*Rot(90,0,0)*Cylinder(diam/2,50)
            tool=tool + Pos(xx+travel/2,0,0)*Rot(90,0,0)*Cylinder(diam/2,50)
            tool=tool + Pos(xx,0,0)*Box(travel,50,diam)
        else:
            continue
        beam = beam - tool
    angle=math.degrees(math.atan2(dy,dx))
    mid=Pos((a[0]+b[0])/2,side*(a[1]+b[1])/2,0)
    return mid*Rot(0,0,angle)*beam

for side in [-1,1]:
    for k in range(len(CENTERLINE)-1):
        a,b=CENTERLINE[k:k+2]
        if k==0:
            holes=[(0.60,"round",18),(0.84,"round",21)]
        elif k==1:
            holes=[(0.4,"round",22)]
        elif k==2:
            holes=[(0.38,"round",24),(0.72,"round",31)]
        else:
            holes=[(0.08,"round",38),(0.13,"round",47),
                   (0.19,"slot",(28,56)),(0.25,"round",34),
                   (0.35,"round",32),(0.44,"round",38),
                   (0.51,"slot",(23,50)),(0.62,"round",29),
                   (0.74,"round",26),(0.82,"round",27)]
        show_object(channel_segment(a,b,side,holes))
    # Steel splice strips: approximated; position and fasteners unmeasured.
    show_object(Pos(830,side*300,0)*Box(140,5,72))
    show_object(Pos(1510,side*760,0)*Box(140,5,72))
    for x,y in [(798,300),(868,300),(1485,760),(1535,760)]:
        show_object(Pos(x,side*(y+8),21)*Rot(90,0,0)*Cylinder(7,12))

# Tongue and hitch: placeholders for layout only.
show_object(Pos(105,0,-12)*Box(140,100,55))
show_object(Pos(75,0,-25)*Rot(90,0,0)*Cylinder(21,105))

# EXISTING transversal square crossmember (non-axle).
cross_y=2*P["straight_half_width"]-70
show_object(Pos(P["crossbar_x"],0,-5)*Box(P["crossbar_section"],cross_y,P["crossbar_section"]))
# Existing welded or bolted connection plates represented separately.
for side in (-1,1):
    show_object(Pos(P["crossbar_x"],side*(P["straight_half_width"]-13),0)*Box(115,12,73))

# Proposed change: new axle is a DIFFERENT component at a DIFFERENT X.
if MODIFIED:
    axle_x=P["new_axle_x"]; axle_z=P["new_axle_z"]
    half=P["straight_half_width"]; L=P["leaf_length"]
    # Rot X 90: default cylinder Z axis becomes longitudinal-to-axle Y axis.
    show_object(Pos(axle_x,0,axle_z)*Rot(90,0,0)*Cylinder(31,2*half+270))
    for side in (-1,1):
        y=side*(half+175)
        show_object(Pos(axle_x,y,axle_z)*Rot(90,0,0)*Cylinder(53,55))
        # Spring packs are approximate 3-leaf arches made from overlapping
        # short rectangular segments. They ARE NOT engineering load models.
        yleaf=side*(half-12)
        for layer,length in enumerate([L,L*.68,L*.41]):
            parts=None
            n=12
            z0=-153.-layer*9
            arch=P["spring_arch"]*(length/L)
            for k in range(n):
                x0=axle_x-length/2+(k/n)*length
                x1=axle_x-length/2+((k+1)/n)*length
                def zfun(x):
                    u=2*(x-axle_x)/L
                    return z0+arch*(1-u*u)
                zm=(zfun(x0)+zfun(x1))/2
                slope=(zfun(x1)-zfun(x0))/(x1-x0)
                s=Pos((x0+x1)/2,yleaf,zm)*Rot(0,-math.degrees(math.atan(slope)),0)*Box(x1-x0+0.9,P["leaf_width"],7)
                parts=s if parts is None else parts+s
            show_object(parts)
        # Hanger plates at spring ends; hypothetical, not approved positions.
        for xx in (axle_x-L/2,axle_x+L/2):
            show_object(Pos(xx,yleaf,-112)*Box(85,72,66))
        # Centre U-bolt retaining plate, visible separated from axle.
        show_object(Pos(axle_x,yleaf,-182)*Box(145,87,15))
