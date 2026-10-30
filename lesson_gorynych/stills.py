"""Stills for the «Змей Горыныч» lesson deck: build steps, part callouts, hero views (headless Blender, Cycles).
usage: python stills.py shots.json outdir [--chunk i --chunks n] [--samples 64] [--lines 1] [--only a,b]
Library: $LDRAW_DIR (official complete) + *.dat next to this script (Studio parts: SPIKE Essential hub, motor...).
"""
import sys, os, json, math, argparse, time, functools
import numpy as np
import bpy, bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('shots'); ap.add_argument('out')
ap.add_argument('--chunk', type=int, default=0); ap.add_argument('--chunks', type=int, default=1)
ap.add_argument('--samples', type=int, default=64)
ap.add_argument('--lines', type=str, default='1')
ap.add_argument('--only', type=str, default='')
ap.add_argument('--model', type=str, default=os.path.join(HERE, 'gorynych.ldr'))
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

# ---------------- LDraw library ----------------
LIB = os.environ.get('LDRAW_DIR', 'ldraw')
INDEX = {}
for sub, pre in (('parts', ''), ('p', ''), ('parts/s', 's\\'), ('p/48', '48\\'), ('p/8', '8\\')):
    d = os.path.join(LIB, sub)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            INDEX.setdefault(pre + fn.lower(), os.path.join(d, fn))
for fn in os.listdir(HERE):                      # Studio-only parts shipped with the lesson
    if fn.lower().endswith('.dat'):
        INDEX[fn.lower()] = os.path.join(HERE, fn)

COLORS = {}
for line in open(os.path.join(LIB, 'LDConfig.ldr'), encoding='utf-8', errors='replace'):
    t = line.split()
    if len(t) > 6 and t[0] == '0' and t[1] == '!COLOUR':
        code = int(t[t.index('CODE') + 1]); v = t[t.index('VALUE') + 1].lstrip('#')
        al = int(t[t.index('ALPHA') + 1]) if 'ALPHA' in t else 255
        COLORS[code] = (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), al)

MISSING = set()
@functools.lru_cache(maxsize=None)
def load(name):
    key = name.strip().lower().replace('/', '\\')
    path = INDEX.get(key)
    if path is None:
        MISSING.add(key); return None
    cs, vs = [], []
    for line in open(path, encoding='utf-8', errors='replace'):
        t = line.split()
        if not t: continue
        if t[0] == '1' and len(t) >= 15:
            c = int(t[1]) if t[1].lstrip('-').isdigit() else 16
            v = list(map(float, t[2:14]))
            sub = load(' '.join(t[14:]))
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
    if not vs:
        return (np.zeros(0, int), np.zeros((0, 3, 3)))
    return (np.concatenate(cs), np.concatenate(vs))

items = []; step = 0
for line in open(a.model, encoding='utf-8'):
    t = line.split()
    if not t: continue
    if t[0] == '0' and len(t) > 1 and t[1] == 'STEP': step += 1
    elif t[0] == '1' and len(t) >= 15:
        v = list(map(float, t[2:14]))
        items.append(dict(color=int(t[1]), pos=np.array(v[0:3]), M=np.array(v[3:12]).reshape(3, 3),
                          part=' '.join(t[14:]), step=step))

S = 0.01
def L2B(p):
    p = np.asarray(p, float)
    return np.stack([p[..., 0], p[..., 2], -p[..., 1]], -1) * S

# ---------------- scene ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = a.samples; sc.cycles.use_adaptive_sampling = True; sc.cycles.use_denoising = True
try: sc.cycles.denoiser = 'OPENIMAGEDENOISE'
except Exception: pass
sc.cycles.max_bounces = 6; sc.cycles.diffuse_bounces = 2; sc.cycles.glossy_bounces = 3
sc.cycles.transmission_bounces = 6; sc.cycles.transparent_max_bounces = 8
sc.render.film_transparent = True
sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA'
sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'; sc.view_settings.exposure = -0.25

w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
bgn = w.node_tree.nodes['Background']; bgn.inputs['Color'].default_value = (1, 1, 1, 1); bgn.inputs['Strength'].default_value = 0.35

if a.lines == '1':
    try:
        sc.render.use_freestyle = True
        sc.render.line_thickness_mode = 'ABSOLUTE'
        vl = sc.view_layers[0]; vl.use_freestyle = True
        fs = vl.freestyle_settings
        ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new('lines')
        ls.select_by_visibility = True; ls.select_by_edge_types = True
        ls.select_silhouette = True; ls.select_border = True; ls.select_crease = True
        st = ls.linestyle; st.color = (0.16, 0.16, 0.18); st.alpha = 0.75; st.thickness = 1.3
    except Exception as e:
        print('freestyle off:', e)

mats = {}
def to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def mat(code):
    code = int(code)
    if code in mats: return mats[code]
    r, g, b, al = COLORS.get(code, (160, 160, 160, 255))
    m = bpy.data.materials.new(f'c{code}'); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (to_lin(r), to_lin(g), to_lin(b), 1)
    p.inputs['Roughness'].default_value = 0.3
    if 'Specular IOR Level' in p.inputs: p.inputs['Specular IOR Level'].default_value = 0.5
    if al < 255:
        p.inputs['Transmission Weight'].default_value = 0.85
        p.inputs['Roughness'].default_value = 0.08
        p.inputs['IOR'].default_value = 1.46
    mats[code] = m
    return m
GHOST = bpy.data.materials.new('ghost'); GHOST.use_nodes = True
gp = GHOST.node_tree.nodes['Principled BSDF']
gp.inputs['Base Color'].default_value = (0.82, 0.85, 0.9, 1); gp.inputs['Alpha'].default_value = 0.16; gp.inputs['Roughness'].default_value = 0.6

def make_obj(name, cs, tris):
    V = L2B(tris).reshape(-1, 3)
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    vv = [bm.verts.new(v) for v in V]
    codes = sorted(set(int(c) for c in cs)); slot = {c: i for i, c in enumerate(codes)}
    for t in range(len(cs)):
        try:
            f = bm.faces.new((vv[3 * t], vv[3 * t + 1], vv[3 * t + 2])); f.material_index = slot[int(cs[t])]
        except ValueError:
            pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0004)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    for c in codes: me.materials.append(mat(c))
    for poly in me.polygons: poly.use_smooth = True
    try: me.set_sharp_from_angle(angle=math.radians(35))
    except Exception: pass
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    ob['codes'] = codes
    return ob

objs = []
for k, it in enumerate(items):
    r = load(it['part'])
    if r is None or len(r[1]) == 0: objs.append(None); continue
    cs = np.where(r[0] == 16, it['color'], r[0]); tris = r[1] @ it['M'].T + it['pos']
    ob = make_obj(f"m{k:03d}_{it['part']}", cs, tris)
    objs.append(dict(ob=ob, step=it['step'], pts=L2B(tris).reshape(-1, 3)))
print('model parts:', len(items), 'missing:', sorted(MISSING), flush=True)

def set_ghost(ob, on):
    me = ob.data
    for i, c in enumerate(ob['codes']):
        me.materials[i] = GHOST if on else mat(c)

# floor (shadow catcher)
bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, 0))
floor = bpy.context.object; floor.is_shadow_catcher = True
fm = bpy.data.materials.new('floor'); floor.data.materials.append(fm)

cam_d = bpy.data.cameras.new('cam'); cam_d.type = 'ORTHO'
cam = bpy.data.objects.new('cam', cam_d); sc.collection.objects.link(cam); sc.camera = cam
lights = []
for nm in ('key', 'fill', 'rim'):
    ld_ = bpy.data.lights.new(nm, 'AREA'); ob = bpy.data.objects.new(nm, ld_); sc.collection.objects.link(ob); lights.append(ob)

def frame(fit_pts, d, W, H, margin=0.07):
    """orthographic camera looking along -d (d = unit vector towards camera, blender space)"""
    mn, mx = fit_pts.min(0), fit_pts.max(0); ctr = Vector(((mn + mx) / 2).tolist()); size = float(np.linalg.norm(mx - mn))
    dist = size * 3
    cam.location = ctr + d * dist
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    R = np.array(cam.matrix_world.to_3x3()); t = np.array(cam.location)
    pc = (fit_pts - t) @ R
    x0, x1 = pc[:, 0].min(), pc[:, 0].max(); y0, y1 = pc[:, 1].min(), pc[:, 1].max()
    cam.location = Vector((t + R[:, 0] * (x0 + x1) / 2 + R[:, 1] * (y0 + y1) / 2).tolist())
    asp = W / H
    span = max(x1 - x0, (y1 - y0) * asp) if asp >= 1 else max((x1 - x0) / asp, y1 - y0)
    cam_d.ortho_scale = span * (1 + 2 * margin)
    cam_d.clip_start = 0.001; cam_d.clip_end = dist + size * 3
    sc.render.resolution_x, sc.render.resolution_y = W, H
    # lights in the camera frame
    rv, uv = Vector(R[:, 0].tolist()), Vector(R[:, 1].tolist())
    L = size
    for ob, off, en, sz in ((lights[0], d * 1.2 - rv * 1.2 + uv * 2.4, 60, 3.0),
                            (lights[1], d * 1.8 + rv * 1.9 + uv * 0.3, 22, 2.5),
                            (lights[2], -d * 1.6 + uv * 2.0 + rv * 0.4, 45, 1.5)):
        ob.location = ctr + off * L
        ob.data.energy = en * L * L; ob.data.size = sz * L
        ob.rotation_euler = (ctr - ob.location).to_track_quat('-Z', 'Y').to_euler()
    return ctr

shots = json.load(open(a.shots))
if a.only.strip():
    keep = set(x.strip() for x in a.only.split(',') if x.strip())
    shots = [s for s in shots if s['name'] in keep]
mine = [s for i, s in enumerate(shots) if i % a.chunks == a.chunk]
print(f'chunk {a.chunk}/{a.chunks}: {len(mine)} shots', flush=True)

part_ob = None
for sh in mine:
    t0 = time.time()
    d = Vector(L2B(np.array(sh['dir'])).tolist()).normalized()
    if part_ob is not None:
        bpy.data.objects.remove(part_ob, do_unlink=True); part_ob = None
    if sh['kind'] == 'part':
        for o in objs:
            if o: o['ob'].hide_render = True
        r = load(sh['part'])
        cs = np.where(r[0] == 16, sh['color'], r[0])
        part_ob = make_obj('part', cs, r[1])
        pts = L2B(r[1]).reshape(-1, 3)
        frame(pts, d, sh['w'], sh['h'], margin=0.06)
        vis_pts = pts
    else:
        hl = set(sh.get('hl', []))
        for o in objs:
            if not o: continue
            o['ob'].hide_render = o['step'] > sh['upto']
            set_ghost(o['ob'], bool(hl) and o['step'] not in hl)
        fit = np.concatenate([o['pts'] for o in objs if o and o['step'] <= sh['fit']])
        frame(fit, d, sh['w'], sh['h'])
        vis_pts = np.concatenate([o['pts'] for o in objs if o and o['step'] <= sh['upto']])
    if a.lines == '1':
        sc.render.use_freestyle = not sh.get('hl')
    floor.hide_render = not sh.get('floor', False)
    floor.location = (float(vis_pts[:, 0].mean()), float(vis_pts[:, 1].mean()), float(vis_pts[:, 2].min()) - 0.0002)
    sc.render.filepath = os.path.join(a.out, sh['name'] + '.png')
    bpy.ops.render.render(write_still=True)
    print(f"done {sh['name']} {time.time() - t0:.1f}s", flush=True)
print('missing:', sorted(MISSING))
