#!/usr/bin/env python3
"""Read-only structural audit for Blockbench cube projects and Java model JSON.
Not a renderer, full schema validator, visibility solver, or runtime benchmark.
"""
import argparse
import base64
import collections
import io
import json
import math
from pathlib import Path
import re
from PIL import Image

FACES = {'north', 'south', 'east', 'west', 'up', 'down'}
PROFILES = ('generic', 'java-legacy', 'java-1.21.6', 'java-26.1')

def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def vector(x, n):
    return isinstance(x, list) and len(x) == n and all(finite(v) for v in x)

def load_json(path):
    def invalid(value):
        raise ValueError('Non-finite JSON constant: ' + value)
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('Duplicate JSON key: ' + k)
            result[k] = v
        return result
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=invalid, object_pairs_hook=pairs)

class Audit:
    def __init__(self, path, profile, assets=None):
        self.path = Path(path).resolve()
        self.profile = profile
        self.assets = Path(assets).resolve() if assets else None
        self.errors, self.warnings, self.textures = [], [], {}
        self.bb = self.path.suffix.lower() == '.bbmodel'
        self.dependencies_complete = True

    def issue(self, code, where, detail, error=False):
        (self.errors if error else self.warnings).append({'code': code, 'where': where, 'detail': detail})

    def asset_path(self, value, kind, suffix):
        if not isinstance(value, str) or not re.fullmatch(r'(?:[a-z0-9_.-]+:)?[a-z0-9_./-]+', value):
            raise ValueError('Invalid resource identifier: ' + repr(value))
        namespace, name = value.split(':', 1) if ':' in value else ('minecraft', value)
        if '..' in name.split('/') or name.startswith('/'):
            raise ValueError('Unsafe resource path: ' + value)
        if not self.assets:
            return None
        return self.assets / namespace / kind / (name + suffix)

    def resolve_model(self, path, stack=()):
        path = path.resolve()
        if path in stack:
            raise ValueError('Model parent cycle')
        if len(stack) > 64:
            raise ValueError('Model parent nesting exceeds audit limit')
        child = load_json(path)
        if not isinstance(child, dict):
            raise ValueError('Model root must be an object')
        parent = child.get('parent')
        merged = {}
        if parent:
            parent_path = self.asset_path(parent, 'models', '.json')
            if parent_path and parent_path.exists():
                merged = self.resolve_model(parent_path, stack + (path,))
            elif parent not in ('builtin/generated', 'minecraft:builtin/generated', 'builtin/entity', 'minecraft:builtin/entity'):
                self.dependencies_complete = False
                self.issue('parent_unresolved', str(path), parent)
        textures = dict(merged.get('textures', {}))
        textures.update(child.get('textures', {}))
        merged.update(child)
        merged['textures'] = textures
        return merged

    def texture_image(self, key, data, meta_path=None, bb_info=None):
        try:
            im = Image.open(io.BytesIO(data)).convert('RGBA')
            w, h = im.size
            alpha = im.getchannel('A').histogram()
            row = {'size': [w, h], 'pixels': w*h, 'rgba_base_bytes': w*h*4,
                   'transparent_pixels': alpha[0], 'partial_alpha_pixels': sum(alpha[1:255]),
                   'frame_size': [w, h], 'frame_count': 1, 'animation_metadata_checked': False}
            if bb_info:
                row['uv_size'] = [bb_info.get('uv_width'), bb_info.get('uv_height')]
            if meta_path and meta_path.exists():
                metadata = load_json(meta_path)
                animation = metadata.get('animation')
                if animation is not None:
                    if not isinstance(animation, dict):
                        raise ValueError('animation must be an object')
                    fw = animation.get('width', w if 'height' in animation else min(w,h))
                    fh = animation.get('height', h if 'width' in animation else min(w,h))
                    if type(fw) is not int or type(fh) is not int or fw <= 0 or fh <= 0 or w%fw or h%fh:
                        raise ValueError('Frame dimensions must be positive integers tiling the PNG')
                    n = w//fw*(h//fh)
                    ft = animation.get('frametime', 1)
                    if type(ft) is not int or ft < 1:
                        raise ValueError('frametime must be a positive integer')
                    if type(animation.get('interpolate', False)) is not bool:
                        raise ValueError('interpolate must be a boolean')
                    frames = animation.get('frames', list(range(n)))
                    if not isinstance(frames, list) or not frames:
                        raise ValueError('frames must be a nonempty list')
                    ticks = 0
                    for f in frames:
                        index = f.get('index') if isinstance(f, dict) else f
                        duration = f.get('time', ft) if isinstance(f, dict) else ft
                        if type(index) is not int or not 0 <= index < n or type(duration) is not int or duration < 1:
                            raise ValueError('Invalid animation frame index or duration')
                        ticks += duration
                    row.update(frame_size=[fw,fh], frame_count=n, timeline_entries=len(frames), duration_ticks=ticks,
                               animation_metadata_checked=True, interpolate=animation.get('interpolate', False))
            elif bb_info and h > w:
                self.issue('animation_metadata_unverified', key, 'Tall embedded PNG is not proof of an exported animation; inspect matching .mcmeta.')
            if sum(alpha[1:255]):
                self.issue('translucency_review', key, 'Partial alpha exists; inspect target render pass and sorting.')
            self.textures[key] = row
        except Exception as exc:
            self.issue('texture_invalid', key, str(exc), True)

    def run(self):
        model = load_json(self.path) if self.bb else self.resolve_model(self.path)
        if not isinstance(model, dict):
            raise ValueError('Model root must be an object')
        es = model.get('elements', [])
        if not isinstance(es, list):
            raise ValueError('elements must be an array')
        texture_map, uv_sizes = {}, {}
        if self.bb:
            ts = model.get('textures', [])
            if not isinstance(ts, list):
                raise ValueError('Blockbench textures must be an array')
            resolution = model.get('resolution', {'width':16,'height':16})
            for i, t in enumerate(ts):
                key = str(i)
                for alias in (i, str(i), t.get('uuid')):
                    if alias is not None:
                        texture_map[alias] = key
                uv_sizes[key] = [t.get('uv_width', resolution.get('width',16)), t.get('uv_height', resolution.get('height',16))]
                source = t.get('source', '')
                candidates = [self.path.parent/t['relative_path']] if t.get('relative_path') else []
                if t.get('path'):
                    candidates.append(Path(t['path']))
                existing = next((p for p in candidates if p.is_file()), None)
                if source.startswith('data:image/png;base64,'):
                    data = base64.b64decode(source.split(',',1)[1], validate=True)
                    if existing:
                        embedded = Image.open(io.BytesIO(data)).convert('RGBA')
                        disk = Image.open(existing).convert('RGBA')
                        if embedded.size != disk.size or embedded.tobytes() != disk.tobytes():
                            self.issue('embedded_disk_mismatch', key, str(existing))
                elif existing:
                    data = existing.read_bytes()
                else:
                    self.issue('texture_missing', key, t.get('name',''), True)
                    continue
                self.texture_image(key, data, Path(str(existing)+'.mcmeta') if existing else None, t)
        else:
            ts = model.get('textures', {})
            for key in ts:
                value, seen = ts[key], {key}
                while isinstance(value, str) and value.startswith('#'):
                    alias = value[1:]
                    if alias in seen:
                        self.issue('texture_alias_cycle', key, alias, True)
                        value = None
                        break
                    seen.add(alias)
                    if alias not in ts:
                        self.issue('texture_alias_missing', key, alias, self.dependencies_complete)
                        value = None
                        break
                    value = ts[alias]
                if value is None:
                    continue
                if isinstance(value, dict):
                    if self.profile != 'java-26.1':
                        self.issue('texture_object_profile', key, 'Sprite objects need a verified target version', True)
                    value = value.get('sprite')
                target = self.asset_path(value, 'textures', '.png')
                texture_map['#'+key] = value
                uv_sizes[value] = [16,16]
                if target and target.exists():
                    if value not in self.textures:
                        self.texture_image(value, target.read_bytes(), Path(str(target)+'.mcmeta'))
                else:
                    external = value.startswith('minecraft:') or ':' not in value
                    self.dependencies_complete = False
                    self.issue('texture_unresolved', key, value, bool(self.assets) and not external)
        stats = collections.Counter()
        duplicate_geometry, duplicate_faces = {}, {}
        for i, e in enumerate(es):
            if not isinstance(e, dict):
                self.issue('element_invalid', str(i), 'Element must be an object', True)
                continue
            where = str(i)+':'+e.get('name','unnamed')
            stats['elements'] += 1
            if e.get('export') is False:
                stats['excluded_elements'] += 1
                continue
            if e.get('type', 'cube') != 'cube':
                self.issue('non_cube_geometry', where, 'Java cuboid export cannot directly represent arbitrary mesh geometry', self.profile != 'generic')
                continue
            lo, hi = e.get('from'), e.get('to')
            if not vector(lo,3) or not vector(hi,3):
                self.issue('invalid_coordinates', where, 'from/to require three finite numbers', True)
                continue
            inflate = e.get('inflate',0) if self.bb else 0
            if not finite(inflate):
                self.issue('invalid_inflate', where, repr(inflate), True)
                continue
            effective = [v-inflate for v in lo]+[v+inflate for v in hi]
            if self.profile != 'generic' and any(v < -16 or v > 32 for v in effective):
                self.issue('java_coordinate_overflow', where, 'Local from/to including inflate exceed [-16,32]', True)
            dims = [b-a for a,b in zip(lo,hi)]
            stats['plane_elements'] += any(abs(x)<1e-9 for x in dims)
            stats['inverted_elements'] += any(x<0 for x in dims)
            em = e.get('light_emission',0)
            if type(em) is not int or not 0 <= em <= 15:
                self.issue('invalid_light_emission', where, 'Expected integer 0..15', True)
            rot = e.get('rotation', [0,0,0] if self.bb else {})
            angles = [0,0,0]
            if self.bb:
                if not vector(rot,3):
                    self.issue('invalid_rotation', where, 'Expected three finite angles', True)
                else:
                    angles = rot
            elif not isinstance(rot,dict):
                self.issue('invalid_rotation', where, 'Expected rotation object', True)
            elif rot:
                if 'origin' in rot and not vector(rot['origin'],3):
                    self.issue('invalid_pivot', where, 'Rotation origin requires three finite numbers', True)
                if 'axis' in rot or 'angle' in rot:
                    if rot.get('axis') not in ('x', 'y', 'z') or not finite(rot.get('angle')):
                        self.issue('invalid_rotation', where, 'Invalid axis/angle', True)
                    else:
                        angles['xyz'.index(rot['axis'])] = rot['angle']
                    if any(k in rot for k in 'xyz'):
                        self.issue('mixed_rotation_notation', where, 'Legacy axis/angle takes precedence; remove ambiguity')
                else:
                    angles = [rot.get(k,0) for k in 'xyz']
                    if not vector(angles,3):
                        self.issue('invalid_rotation', where, 'Expected finite x/y/z angles', True)
                        angles = [0,0,0]
                    if self.profile in ('java-legacy','java-1.21.6'):
                        self.issue('multi_axis_notation_profile', where, 'XYZ notation unavailable in this profile', True)
            active = [a for a in angles if abs(a)>1e-9]
            stats['rotated_elements'] += bool(active)
            if self.profile in ('java-legacy','java-1.21.6') and (len(active)>1 or any(abs(a)>45 for a in active)):
                self.issue('rotation_profile_violation', where, 'Profile permits one axis within [-45,45]', True)
            if self.profile == 'java-legacy' and any(abs(a/22.5-round(a/22.5))>1e-6 for a in active):
                self.issue('legacy_angle_step', where, 'Profile requires 22.5 degree steps', True)
            fs = e.get('faces', {})
            if not isinstance(fs,dict):
                self.issue('invalid_faces', where, 'faces must be an object', True)
                continue
            used_faces = {}
            for side, face in fs.items():
                if not isinstance(face,dict):
                    self.issue('invalid_face', where+'/'+side, 'Expected object', True)
                    continue
                if side not in FACES:
                    self.issue('invalid_face_side', where, side, True)
                ref = face.get('texture')
                if ref is None:
                    if not self.bb:
                        self.issue('missing_face_texture', where+'/'+side, 'Omit non-rendered Java faces instead of null texture', True)
                    continue
                stats['declared_export_faces'] += 1
                used_faces[side] = face
                try:
                    key = texture_map.get(ref)
                except TypeError:
                    key = None
                if key is None:
                    self.issue('face_texture_unresolved', where+'/'+side, str(ref), self.bb or self.dependencies_complete)
                    continue
                uv = face.get('uv')
                if uv is not None:
                    if not vector(uv,4):
                        self.issue('invalid_uv', where+'/'+side, 'UV needs four finite numbers', True)
                    else:
                        size = uv_sizes[key]
                        if any(not finite(v) or v<=0 for v in size):
                            self.issue('invalid_uv_size', str(key), str(size), True)
                        elif any(v < 0 or v > size[j%2] for j,v in enumerate(uv)):
                            self.issue('uv_outside_texture', where+'/'+side, {'uv':uv,'logical_size':size})
                if face.get('rotation',0) not in [0,90,180,270]:
                    self.issue('invalid_face_rotation', where+'/'+side, 'Expected 0/90/180/270', True)
                if not active and not any(x<0 for x in dims) and side in FACES:
                    axis, sign = {'west':(0,0),'east':(0,1),'down':(1,0),'up':(1,1),'north':(2,0),'south':(2,1)}[side]
                    other = [j for j in range(3) if j!=axis]
                    if all(dims[j]>0 for j in other):
                        signature = (axis, sign, round((hi if sign else lo)[axis],7), *[round(a[j],7) for j in other for a in (lo,hi)])
                        if signature in duplicate_faces:
                            stats['coincident_unrotated_face_candidates'] += 1
                        duplicate_faces[signature] = where
            if not used_faces:
                stats['faceless_elements'] += 1
            signature = json.dumps({k:e.get(k) for k in ('from','to','rotation','origin','inflate','shade','light_emission','faces')},sort_keys=True)
            if signature in duplicate_geometry:
                stats['exact_duplicate_element_candidates'] += 1
            duplicate_geometry[signature] = where
        if stats['inverted_elements']:
            self.issue('inverted_geometry_review', 'model', 'May be intentional outline shells; verify winding, pairing and runtime culling. Never auto-sort bounds.')
        if stats['coincident_unrotated_face_candidates']:
            self.issue('coplanar_candidates', 'model', 'Exact unrotated rectangles coincide; may be intentional layers/phases, not proof of z-fighting.')
        extras = model.get('unhandled_root_fields', {})
        if self.bb and (model.get('animations') or extras.get('compact_motion_b64') or extras.get('aeons_motion_json')):
            self.issue('runtime_animation_not_verified', 'model', 'Only editable geometry inspected; separately validate the actual runtime export and motion driver.')
        if self.bb and self.profile != 'generic':
            self.issue('editor_is_not_export', 'model', 'Groups, animation, pivots, inflate and editor materials must be checked after Java export.')
        return {'path':str(self.path),'profile':self.profile,'kind':'bbmodel' if self.bb else 'java-model',
                'structural_errors_absent':not self.errors,'dependencies_complete':self.dependencies_complete,
                'counts':dict(stats),'textures':self.textures,'texture_pixels':sum(t['pixels'] for t in self.textures.values()),
                'errors':self.errors,'warnings':self.warnings,
                'limitations':['No Minecraft client render or FPS measurement','No full schema validation or arbitrary overlap/hidden-face proof',
                               'No custom animation expansion, bone transform baking or outline pairing verification','Pack version, item definitions and display contexts require separate checks']}

def audit(path, profile='java-26.1', assets=None):
    return Audit(path,profile,assets).run()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model',type=Path)
    parser.add_argument('--profile',choices=PROFILES,required=True)
    parser.add_argument('--assets-root',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        report=audit(args.model,args.profile,args.assets_root)
    except Exception as exc:
        report={'structural_errors_absent':False,'errors':[{'code':'input_invalid','detail':str(exc)}]}
    data=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        out = args.output.resolve()
        if out.suffix.lower() != '.json':
            parser.error('Output must be a .json report')
        if out == args.model.resolve():
            parser.error('Output must not overwrite input')
        if args.assets_root and out.is_relative_to(args.assets_root.resolve()):
            parser.error('Write reports outside the input assets directory')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(data,encoding='utf-8')
    print(data)
    return 0 if report['structural_errors_absent'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
