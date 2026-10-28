"""Shared bounded input and no-clobber output helpers."""
import json
import os
from pathlib import Path
import tempfile
from audit_model import load_json, finite, vector

def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data if isinstance(data, bytes) else (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    with path.open('xb') as f:
        f.write(payload)

def safe_relative(value):
    if not isinstance(value, str):
        raise ValueError('Expected a relative path string')
    p = Path(value)
    if not value or '\\' in value or p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')):
        raise ValueError('Expected a confined relative path: '+repr(value))
    return p

def confined(root, name):
    root = Path(root).resolve()
    p = root / safe_relative(name)
    if not p.resolve().is_relative_to(root):
        raise ValueError('Path escapes source root: '+name)
    return p

def new_bundle(output, build):
    """Build everything in staging; publish a new directory, never replace inputs."""
    output = Path(output).absolute()
    if output.exists():
        raise ValueError('Output already exists: '+str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.item-stage-', dir=output.parent) as temp:
        stage = Path(temp)/'bundle'; stage.mkdir()
        result = build(stage)
        if output.exists():
            raise ValueError('Output appeared during build')
        os.rename(stage, output)
    return result

def selected_cubes(model, ids):
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        raise ValueError('element_ids must be a nonempty unique list')
    all_ids = [e.get('uuid') for e in model.get('elements', [])]
    if len(all_ids) != len(set(all_ids)) or any(not isinstance(x,str) or not x for x in all_ids):
        raise ValueError('Every element needs a unique UUID')
    lookup = {e['uuid']:e for e in model['elements']}
    if any(i not in lookup for i in ids):
        raise ValueError('Unknown element UUID')
    chosen = [lookup[i] for i in ids]
    for e in chosen:
        if e.get('type','cube') != 'cube' or not vector(e.get('from'),3) or not vector(e.get('to'),3):
            raise ValueError('Only finite cuboids supported')
    return chosen
