"""Reel «Змей Горыныч»: parts drop by steps -> drives to the mountain -> turns -> back home -> parts fly away (loop).
Headless Blender (bpy), Cycles, real scale (1 LDU = 0.4 mm). Animation is computed per frame in a handler (no fcurves).
usage:
  python reel.py out --frames 0,120,186          # list or range a-b
  python reel.py out --chunk 3 --chunks 20       # contiguous part of 0..N-1
  python reel.py out --stills                    # post images (vk 1080x1350, tg 1280x960)
"""
import sys, os, math, argparse, time, functools, random
import numpy as np
import bpy, bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('out')
ap.add_argument('--frames', default='')
ap.add_argument('--chunk', type=int, default=0); ap.add_argument('--chunks', type=int, default=1)
ap.add_argument('--samples', type=int, default=48)
ap.add_argument('--res', type=int, default=100)
ap.add_argument('--stills', action='store_true')
ap.add_argument('--model', default=os.path.join(HERE, 'gorynych.ldr'))
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

FPS, N = 30, 480
S = 0.0004                       # metres per LDU
def B(x, y, z): return Vector((x * S, y * S, z * S))   # Blender coords given in LDU

# ---------------- LDraw ----------------
LIB = os.environ.get('LDRAW_DIR', 'ldraw')
INDEX = {}
for sub, pre in (('parts', ''), ('p', ''), ('parts/s', 's\\'), ('p/48', '48\\'), ('p/8', '8\\')):
    d = os.path.join(LIB, sub)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            INDEX.setdefault(pre + fn.lower(), os.path.join(d, fn))
for fn in os.listdir(HERE):
    if fn.lower().endswith('.dat'):
        INDEX[fn.lower()] = os.path.join(HERE, fn)
COLORS = {}
for line in open(os.path.join(LIB, 'LDConfig.ldr'), encoding='utf-8', errors='replace'):
    t = line.split()
    if len(t) > 6 and t[0] == '0' and t[1] == '!COLOUR':
        code = int(t[t.index('CODE') + 1]); v = t[t.index('VALUE') + 1].lstrip('#')
        COLORS[code] = (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
MISSING = set()
@functools.lru_cache(maxsize=None)
def load(name):
    path = INDEX.get(name.strip().lower().replace('/', '\\'))
    if path is None:
        MISSING.add(name); return None
    cs, vs = [], []
    for line in open(path, encoding='utf-8', errors='replace'):
        t = line.split()
        if not t: continue
        if t[0] == '1' and len(t) >= 15:
            c = int(t[1]) if t[1].lstrip('-').isdigit() else 16
            v = list(map(float, t[2:14])); sub = load(' '.join(t[14:]))
            if sub is None or len(sub[1]) == 0: continue
            M = np.array(v[3:12]).reshape(3, 3); T = np.array(v[0:3])
            cs.append(np.where(sub[0] == 16, c, sub[0])); vs.append(sub[1] @ M.T + T)
        elif t[0] == '3' and len(t) >= 11:
            c = int(t[1]) if t[1].lstrip('-').isdigit() else 16
            cs.append(np.array([c])); vs.append(np.array(list(map(float, t[2:11]))).reshape(1, 3, 3))
        elif t[0] == '4' and len(t) >= 14:
            c = int(t[1]) if t[1].lstrip('-').isdigit() else 16
            q = np.array(list(map(float, t[2:14]))).reshape(4, 3)
            cs.append(np.array([c, c])); vs.append(np.stack([q[[0, 1, 2]], q[[0, 2, 3]]]))
    if not vs: return (np.zeros(0, int), np.zeros((0, 3, 3)))
    return (np.concatenate(cs), np.concatenate(vs))

items = []; step = 0
for line in open(a.model, encoding='utf-8'):
    t = line.split()
    if not t: continue
    if t[0] == '0' and len(t) > 1 and t[1] == 'STEP': step += 1
    elif t[0] == '1' and len(t) >= 15:
        v = list(map(float, t[2:14]))
        items.append(dict(color=int(t[1]), pos=np.array(v[0:3]), M=np.array(v[3:12]).reshape(3, 3),
                          part=' '.join(t[14:]).lower(), step=step))
NSTEP = max(i['step'] for i in items) + 1

def L2B(p):            # LDraw (y down) -> Blender LDU (z up)
    p = np.asarray(p, float); return np.stack([p[..., 0], p[..., 2], -p[..., 1]], -1)

# ---------------- scene ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = a.samples; sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.02
sc.cycles.use_denoising = True
try: sc.cycles.denoiser = 'OPENIMAGEDENOISE'
except Exception: pass
sc.cycles.max_bounces = 6; sc.cycles.diffuse_bounces = 3; sc.cycles.glossy_bounces = 3
sc.render.use_persistent_data = True
sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.5
sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 95
sc.render.fps = FPS
for vt in ('AgX', 'Filmic'):
    try: sc.view_settings.view_transform = vt; break
    except Exception: pass
for lk in ('AgX - Medium High Contrast', 'Medium High Contrast', 'AgX - Punchy'):
    try: sc.view_settings.look = lk; break
    except Exception: pass
sc.view_settings.exposure = 0.0

w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes['Background']; bg.inputs['Color'].default_value = (0.80, 0.81, 0.84, 1); bg.inputs['Strength'].default_value = 0.9

def lin(c): c = c / 255.0; return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
mats = {}
def lego_mat(code):
    if code in mats: return mats[code]
    r, g, b = COLORS.get(code, (160, 160, 160))
    m = bpy.data.materials.new(f'c{code}'); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (lin(r), lin(g), lin(b), 1)
    p.inputs['Roughness'].default_value = 0.2
    if 'Specular IOR Level' in p.inputs: p.inputs['Specular IOR Level'].default_value = 0.5
    mats[code] = m; return m

def node_mat(name, base, rough, noise_amp=0.0, noise_scale=300.0, bump=0.0, wave=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; p = nt.nodes['Principled BSDF']
    p.inputs['Roughness'].default_value = rough
    tc = nt.nodes.new('ShaderNodeTexCoord')
    if wave:
        mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1.0, 0.035, 1.0)
        nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
        wv = nt.nodes.new('ShaderNodeTexNoise'); wv.inputs['Scale'].default_value = wave[0]
        wv.inputs['Detail'].default_value = 9.0; wv.inputs['Roughness'].default_value = 0.62
        wv.inputs['Distortion'].default_value = wave[1]
        nt.links.new(mp.outputs['Vector'], wv.inputs['Vector'])
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.68
        ramp.color_ramp.elements[0].color = wave[2]; ramp.color_ramp.elements[1].color = wave[3]
        nt.links.new(wv.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], p.inputs['Base Color'])
        src = wv.outputs['Fac']
    else:
        nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = noise_scale
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = tuple(c * (1 - noise_amp) for c in base[:3]) + (1,)
        ramp.color_ramp.elements[1].color = base
        nt.links.new(nz.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], p.inputs['Base Color'])
        src = nz.outputs['Fac']
    if bump > 0:
        bn = nt.nodes.new('ShaderNodeBump'); bn.inputs['Strength'].default_value = bump
        bn.inputs['Distance'].default_value = 0.0004
        nt.links.new(src, bn.inputs['Height']); nt.links.new(bn.outputs['Normal'], p.inputs['Normal'])
    return m

def mesh_obj(name, verts, faces, mat, smooth=False):
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(v) for v in verts], [], faces); me.update()
    me.materials.append(mat)
    for poly in me.polygons: poly.use_smooth = smooth
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); return ob

def lego_obj(name, cs, tris):
    V = (L2B(tris) * S).reshape(-1, 3)
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    vv = [bm.verts.new(v) for v in V]
    codes = sorted(set(int(c) for c in cs)); slot = {c: i for i, c in enumerate(codes)}
    for k in range(len(cs)):
        try:
            f = bm.faces.new((vv[3 * k], vv[3 * k + 1], vv[3 * k + 2])); f.material_index = slot[int(cs[k])]
        except ValueError: pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.04 * S)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    for c in codes: me.materials.append(lego_mat(c))
    for poly in me.polygons: poly.use_smooth = True
    try: me.set_sharp_from_angle(angle=math.radians(35))
    except Exception: pass
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); return ob

def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None); sc.collection.objects.link(e); e.location = loc
    if parent is not None:
        e.parent = parent; e.matrix_parent_inverse = parent.matrix_world.inverted()
    bpy.context.view_layer.update(); return e

# ---------------- layout (LDU, Blender axes, z up) ----------------
GZ = -68.0                    # ground
Y0 = 20.0                     # robot pivot (middle of the axle) at start
R_WHEEL, HALF_TRACK = 38.0, 115.0
V_FWD = math.pi * HALF_TRACK / FPS          # LDU/frame: same motor speed turns 180 deg in 1 s
D = V_FWD * 60                              # 2 s forward
F_BUILD, STEP_DT, DROP = 30, 3.6, 9
F_GO, F_TURN, F_BACK, F_HOME = 186, 246, 306, 366
F_OUT = 446
MOUNT_Y = Y0 - D - 600

robot = empty('robot', B(0, Y0, GZ))
wheel_e = {s: empty(f'wheel{s}', B(s * HALF_TRACK, Y0, -30), robot) for s in (1, -1)}

parts = []
for k, it in enumerate(items):
    r = load(it['part'])
    if r is None or len(r[1]) == 0: continue
    cs = np.where(r[0] == 16, it['color'], r[0]); tris = r[1] @ it['M'].T + it['pos']
    ob = lego_obj(f"p{k:03d}", cs, tris)
    side = 0
    nm = it['part']; p = it['pos']
    if nm in ('4185.dat', '2815.dat', '3705.dat') or (nm == '3713.dat' and abs(p[1] - 30) < 1 and abs(p[2] - 20) < 1):
        side = 1 if p[0] > 0 else -1
    par = wheel_e[side] if side else robot
    ob.parent = par; ob.matrix_parent_inverse = par.matrix_world.inverted()
    parts.append(dict(ob=ob, step=it['step'], side=side, base=ob.location.copy(), k=k))
print('model parts:', len(parts), 'steps:', NSTEP, 'missing:', sorted(MISSING), flush=True)

# desk
wood = node_mat('wood', None, 0.38, bump=0.008,
                wave=(55.0, 1.5, (0.60, 0.43, 0.27, 1), (0.74, 0.56, 0.37, 1)))
X0, X1, YA, YB = -2600, 2600, -3200, 2600
desk = mesh_obj('desk', [B(X0, YA, GZ), B(X1, YA, GZ), B(X1, YB, GZ), B(X0, YB, GZ)], [(0, 1, 2, 3)], wood)
wall_m = node_mat('wall', (0.58, 0.64, 0.62, 1), 0.9, noise_amp=0.08, noise_scale=8.0)
mesh_obj('wall', [B(-6000, YA, GZ - 50), B(6000, YA, GZ - 50), B(6000, YA, 4000), B(-6000, YA, 4000)], [(0, 1, 2, 3)], wall_m)

# masking tape
tape = node_mat('tape', (0.84, 0.76, 0.55, 1), 0.75, noise_amp=0.25, noise_scale=900.0, bump=0.03)
TW = 47.0
def strip(x0, y0, x1, y1, name):
    z = GZ + 0.6
    mesh_obj(name, [B(x0, y0, z), B(x1, y0, z), B(x1, y1, z), B(x0, y1, z)], [(0, 1, 2, 3)], tape)
START_Y = Y0 - 175
strip(-300, START_Y - TW / 2, 300, START_Y + TW / 2, 'start')
yy = START_Y - 110; n = 0
while yy - 90 > MOUNT_Y + 330:
    for s in (-1, 1):
        strip(s * 270 - TW / 2, yy - 90, s * 270 + TW / 2, yy, f'dash{n}_{s}')
    yy -= 150; n += 1

# cardboard mountain with a paper snow cap
rnd = random.Random(7)
card = node_mat('card', (0.47, 0.33, 0.19, 1), 0.88, noise_amp=0.35, noise_scale=180.0, bump=0.05)
paper = node_mat('paper', (0.90, 0.90, 0.88, 1), 0.7, noise_amp=0.05, noise_scale=400.0)
NM, RM, HM = 9, 270.0, 430.0
apex = B(25, MOUNT_Y - 20, GZ + HM)
ring = []
for i in range(NM):
    ang = 2 * math.pi * i / NM + rnd.uniform(-0.12, 0.12); rr = RM * rnd.uniform(0.82, 1.08)
    ring.append(B(rr * math.cos(ang), MOUNT_Y + rr * math.sin(ang), GZ))
mesh_obj('mount', ring + [apex], [(i, (i + 1) % NM, NM) for i in range(NM)] + [tuple(range(NM - 1, -1, -1))], card)
capv = []
for i in range(NM):
    f = rnd.uniform(0.55, 0.68)
    v = apex.lerp(ring[i], f); c = Vector((apex.x, apex.y, v.z))
    capv.append(c + (v - c) * 1.03)
capapex = apex + Vector((0, 0, 0.0004))
mesh_obj('cap', capv + [capapex], [(i, (i + 1) % NM, NM) for i in range(NM)], paper)

# lights
sun_d = bpy.data.lights.new('sun', 'SUN'); sun_d.energy = 3.2; sun_d.angle = math.radians(4); sun_d.color = (1.0, 0.94, 0.86)
sun = bpy.data.objects.new('sun', sun_d); sc.collection.objects.link(sun)
sun.rotation_euler = Vector((-0.55, -0.7, -1.0)).to_track_quat('-Z', 'Y').to_euler()

# camera
cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 35; cam_d.sensor_fit = 'AUTO'; cam_d.sensor_width = 36
cam_d.clip_start = 0.002; cam_d.clip_end = 20
cam = bpy.data.objects.new('cam', cam_d); sc.collection.objects.link(cam); sc.camera = cam
tgt = empty('target', B(0, 0, 0))
con = cam.constraints.new('TRACK_TO'); con.target = tgt; con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
cam_d.dof.use_dof = True; cam_d.dof.focus_object = tgt; cam_d.dof.aperture_fstop = 11.0

# camera keys: frame -> (camera, target) in LDU
CK = [(0, (420, 900, 60), (0, -400, 80)),
      (30, (380, 820, 140), (0, 0, 130)),
      (110, (-460, 700, 260), (0, 20, 140)),
      (180, (380, 640, 170), (0, -20, 140)),
      (222, (650, -280, 130), (0, -380, 130)),
      (250, (480, -420, 160), (0, Y0 - D, 130)),
      (306, (-470, -380, 180), (0, Y0 - D, 130)),
      (338, (-500, 120, 130), (0, -330, 130)),
      (372, (300, 760, 150), (0, 0, 140)),
      (420, (420, 900, 60), (0, -400, 80)),
      (N, (420, 900, 60), (0, -400, 80))]
def catmull(keys, t):
    fr = [k[0] for k in keys]
    if t <= fr[0]: return np.array(keys[0][1], float)
    if t >= fr[-1]: return np.array(keys[-1][1], float)
    i = max(j for j in range(len(fr) - 1) if fr[j] <= t)
    p = [np.array(keys[max(0, min(len(keys) - 1, i + o))][1], float) for o in (-1, 0, 1, 2)]
    u = (t - fr[i]) / (fr[i + 1] - fr[i]); u = u * u * (3 - 2 * u) * 0.35 + u * 0.65
    return 0.5 * (2 * p[1] + (-p[0] + p[2]) * u + (2 * p[0] - 5 * p[1] + 4 * p[2] - p[3]) * u * u + (-p[0] + 3 * p[1] - 3 * p[2] + p[3]) * u ** 3)

def trap(t, T, L, r):
    t = min(max(t, 0.0), T); vmax = L / (T - r)
    if t < r: return 0.5 * vmax * t * t / r
    if t < T - r: return 0.5 * vmax * r + vmax * (t - r)
    tt = T - t; return L - 0.5 * vmax * tt * tt / r

def pose(t):
    s1 = trap(t - F_GO, 60, D, 6)
    ph = math.pi * trap(t - F_TURN, 60, 1.0, 9)
    s3 = trap(t - F_BACK, 60, D, 6)
    y = Y0 - s1 + s3
    sP = s1 - ph * HALF_TRACK + s3          # wheel at +x
    sM = s1 + ph * HALF_TRACK + s3          # wheel at -x
    return y, ph, sP / R_WHEEL, sM / R_WHEEL

def step_start(k): return F_BUILD + STEP_DT * k
def out_start(k): return F_OUT + (NSTEP - 1 - k) * 0.55

STILL = None
def apply(t):
    y, ph, aP, aM = pose(t)
    robot.location = B(0, y, GZ); robot.rotation_euler = (0, 0, ph)
    wheel_e[1].rotation_euler = (aP, 0, 0); wheel_e[-1].rotation_euler = (aM, 0, 0)
    Rz = Matrix.Rotation(ph, 3, 'Z')
    Rw = {1: Rz @ Matrix.Rotation(aP, 3, 'X'), -1: Rz @ Matrix.Rotation(aM, 3, 'X'), 0: Rz}
    for pt in parts:
        k = pt['step']; s0 = step_start(k); o0 = out_start(k)
        dz = 0.0; vis = t >= s0
        if s0 <= t < s0 + DROP:
            u = (t - s0) / DROP; dz = 300.0 * (1 - u) ** 3
        if t >= o0:
            u = (t - o0) / 8.0
            if u >= 1: vis = False
            else: dz = 1100.0 * u * u
        ob = pt['ob']; ob.hide_render = not vis
        ob.location = pt['base'] + Rw[pt['side']].inverted() @ Vector((0, 0, dz * S))
    if STILL is None:
        c = catmull(CK, t); g = catmull([(k[0], k[2]) for k in CK], t)
    else:
        c, g = STILL
    cam.location = B(*c); tgt.location = B(*g)

def handler(scene, depsgraph=None):
    apply(scene.frame_current + scene.frame_subframe)
bpy.app.handlers.frame_change_pre.append(handler)

sc.frame_start, sc.frame_end = 0, N - 1
sc.render.resolution_percentage = a.res

def render_frame(f, path):
    sc.frame_set(f); apply(f)
    sc.render.filepath = path
    t0 = time.time(); bpy.ops.render.render(write_still=True)
    print(f'done {os.path.basename(path)} {time.time() - t0:.1f}s', flush=True)

if a.stills:
    sc.render.use_motion_blur = False
    sc.cycles.samples = max(a.samples, 96)
    for name, (W, H), f, c, g, lens in (('post', (1600, 1200), 330, (720, 380, 140), (150, -560, 150), 35),):
        cam_d.lens = lens
        sc.render.resolution_x, sc.render.resolution_y = W, H
        STILL = (c, g)
        y, ph, _, _ = pose(f)
        cam_d.dof.focus_object = None
        cam_d.dof.focus_distance = (B(*c) - B(0, y, 130)).length
        render_frame(f, os.path.join(a.out, f'{name}.jpg'))
    STILL = None
else:
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
    if a.frames.strip():
        fr = []
        for x in a.frames.split(','):
            x = x.strip()
            if '-' in x: lo, hi = map(int, x.split('-')); fr += list(range(lo, hi + 1))
            elif x: fr.append(int(x))
        fr = [f for i, f in enumerate(fr) if i % a.chunks == a.chunk]
    else:
        per = math.ceil(N / a.chunks); fr = list(range(a.chunk * per, min(N, (a.chunk + 1) * per)))
    print(f'chunk {a.chunk}/{a.chunks}: frames {fr[:1]}..{fr[-1:]} ({len(fr)})', flush=True)
    for f in fr:
        render_frame(f, os.path.join(a.out, f'f{f:04d}.jpg'))
print('missing:', sorted(MISSING))
