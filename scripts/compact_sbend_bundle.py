"""Compact explicitly selected JNU S-bend bundles using a JSON job.

Run in full KLayout: klayout_app.exe -b -r this.py -rd job_file=job.json
See references/sbend-bundles.md. All layout paths and device selectors belong
in the job, never in this reusable script. Output is verified before publication.
"""
import importlib
import json
import math
import os
from pathlib import Path
import re
import sys
import traceback
from collections import Counter
import pya

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout_checks import instance_key, instances, shapes, unchanged_cells, optical_checks


def require(condition, message):
    if not condition:
        raise ValueError(message)


def select(root, selector):
    require('expected_count' in selector, 'Every selector needs expected_count')
    require(any(k in selector for k in ('cell_name', 'property', 'origin_um')),
            'An explicit selector is required')
    found = []
    for i in root.each_inst():
        if 'cell_name' in selector and i.cell.name != selector['cell_name']:
            continue
        if 'origin_um' in selector:
            x, y = selector['origin_um']; v = i.dcplx_trans.disp
            if abs(v.x-x) > root.layout().dbu/2 or abs(v.y-y) > root.layout().dbu/2:
                continue
        if 'property' in selector:
            require(('equals' in selector) != ('regex' in selector),
                    'Property selector needs exactly one of equals or regex')
            value = str(i.property(selector['property']))
            if 'equals' in selector and value != str(selector['equals']):
                continue
            if 'regex' in selector and re.fullmatch(selector['regex'], value) is None:
                continue
        found.append(i)
    require(len(found) == selector['expected_count'],
            'Selector count mismatch: %s; found %s' % (selector, len(found)))
    return found


def bootstrap(job):
    for path in reversed(job.get('python_paths', [])):
        sys.path.insert(0, str(Path(path).resolve()))
    importlib.import_module(job.get('bootstrap_module', 'JNULib'))
    # Coercion must derive geometry without persisting task-specific global defaults.
    for name, module in list(sys.modules.items()):
        if name.startswith('JNU_MWP_pcells.') and hasattr(module, 'save_pcell_defaults'):
            module.save_pcell_defaults = lambda *a, **kw: None
    return importlib.import_module('JNU_MWP_tools.actions.path_to_waveguide')


def read(path, wg):
    layout = pya.Layout()
    for name in ('Waveguide', 'Composite_Waveguide'):
        wg._ensure_local_waveguide_pcell(layout, name)
    layout.read(str(path))
    return layout


def run(job):
    source = Path(job['input_file']).resolve()
    output = Path(job['output_file']).resolve()
    candidate = output.with_name(output.stem + '.candidate' + output.suffix)
    require(source != output, 'Use a separate output file')
    require(not output.exists() and not candidate.exists(), 'Output or candidate already exists')
    require(output.parent.is_dir(), 'Output parent directory must exist')
    report_path = Path(job['report_file']).resolve() if job.get('report_file') else None
    if report_path is not None:
        require(report_path not in (source, output, candidate), 'Report must not overwrite a layout')
        require(report_path.parent.is_dir(), 'Report parent directory must exist')
    span = float(job['new_span_um']); limit = float(job['minimum_radius_um'])
    require(span > 0 and limit > 0, 'Span and radius must be positive')
    wg = bootstrap(job)
    layout = read(source, wg); root = layout.cell(job['parent_cell'])
    require(root is not None, 'Parent cell not found')
    old_names = {c.name for c in layout.each_cell()}
    original_shapes = shapes(layout, root)
    all_before = instances(root)
    selected_before = Counter(); selected_after = Counter()
    touched = []; replaced = set(); plans = []
    lib = pya.Library.library_by_name(job.get('library_name', 'JNULib'))
    require(lib is not None, 'S-bend library not loaded')
    pid = lib.layout().pcell_id(job.get('sbend_pcell', 'Pcell_S_Bend'))
    require(pid is not None, 'S-bend declaration not found')
    declaration = lib.layout().pcell_declaration(pid)

    def claim(i):
        require(not any(i == old for old in touched), 'Overlapping mutation selectors')
        touched.append(i)
        selected_before[instance_key(i)] += 1

    def move(i, dx):
        i.cplx_trans = pya.ICplxTrans(1, 0, False, round(dx/layout.dbu), 0) * i.cplx_trans

    # Resolve every target and curvature constraint before touching any instance.
    for group in job['groups']:
        sbends = select(root, group['sbends'])
        translate = [i for s in group.get('translate', []) for i in select(root, s)]
        reconnect = [(i, a['point_indices']) for a in group.get('reconnect', [])
                     for i in select(root, a['selector'])]
        variants = []; shifts = []
        for i in sbends:
            require(i.cell.is_pcell_variant(), 'Selected S-bend is not a PCell')
            require(i.cell.pcell_library() is not None and i.cell.pcell_library().name() == lib.name(),
                    'Selected S-bend belongs to a different library')
            require(i.cell.pcell_declaration().name() == declaration.name(),
                    'Selected PCell is not the configured S-bend declaration')
            p = dict(i.cell.pcell_parameters_by_name())
            require(p.get('bend_type') == 'Bezier' and all(k in p for k in ('length','height','width','bezier')),
                    'Only Bezier S-bends are supported')
            require(p['length'] > span, 'New span must be shorter than existing span')
            tr = i.dcplx_trans
            a = tr * pya.DPoint(0, 0); b = tr * pya.DPoint(p['length'], 0)
            require(abs(tr.mag-1) < 1e-10 and abs(b.y-a.y) < layout.dbu/2,
                    'Only unit-scale horizontal bundles are supported')
            direction = 1 if b.x > a.x else -1
            shifts.append(direction * (span-p['length']))
            p.update(length=span, npoints=0)
            values = declaration.coerce_parameters(layout, wg._local_pcell_parameter_values(declaration, p))
            actual = dict(zip((q.name for q in declaration.get_parameters()), values))
            radius = float(actual['Bezier_Rmin'])
            require(abs(p['height']) < 1e-12 or radius > limit,
                    'Minimum radius %.9g um does not exceed %.9g um' % (radius, limit))
            variants.append((i, values, p['height'], radius))
        require(shifts and max(shifts)-min(shifts) < layout.dbu/2,
                'One bundle must have a common old span and direction')
        dx = round(shifts[0]/layout.dbu)*layout.dbu
        plans.append((group['id'], variants, translate, reconnect, dx))
    for _, variants, translate, reconnect, _ in plans:
        for i in [v[0] for v in variants] + translate + [r[0] for r in reconnect]:
            claim(i)

    radii = []; group_reports = []
    for name, variants, translate, reconnect, dx in plans:
        for i, values, height, radius in variants:
            replaced.add(i.cell_index)
            i.cell_index = layout.add_pcell_variant(lib, pid, values)
            if abs(height) > 1e-12:
                radii.append(radius)
        for i in translate:
            move(i, dx)
        for i, indices in reconnect:
            old = i.cell; require(old.is_pcell_variant(), 'Reconnect requires a Waveguide PCell')
            require(abs(i.dcplx_trans.mag-1) < 1e-10, 'Reconnect requires unit-scale waveguides')
            p = dict(old.pcell_parameters_by_name())
            require(all(k in p for k in ('path','width','bend_type')), 'Reconnect needs a single-width Waveguide')
            points = [i.dcplx_trans * q for q in p['path'].each_point()]
            require(len(indices) == len(set(indices)) and all(0 <= k < len(points) for k in indices),
                    'Invalid reconnect point indices')
            for k in indices:
                points[k] = pya.DPoint(points[k].x+dx, points[k].y)
            require(all(abs(a.x-b.x) < layout.dbu/2 or abs(a.y-b.y) < layout.dbu/2
                        for a,b in zip(points, points[1:])), 'Reconnect produced a diagonal segment')
            radius = p['Euler_Reff'] if p['bend_type'] == 'Euler' else p['radius']
            for j,(a,b) in enumerate(zip(points,points[1:])):
                need = radius * ((j > 0) + (j < len(points)-2))
                require(math.hypot(a.x-b.x,a.y-b.y)+layout.dbu/2 >= need,
                        'Reconnect cannot fit the existing bend radii')
            params = {'width':p['width'], 'radius':p['radius'], 'bend_type':p['bend_type'],
                      'bezier':p['bezier_k'], 'Euler_Rmax':p['Euler_Rmax'],
                      'Euler_Rmin':p['Euler_Rmin'], 'waveguide_layer':str(p['waveguide_layer'])}
            c0 = wg._create_waveguide_cell(layout, pya.DPath(points,p['width']), params,0)
            dec, local_pid = wg._ensure_local_waveguide_pcell(layout,'Waveguide')
            values = dec.coerce_parameters(layout,wg._local_pcell_parameter_values(dec,c0.pcell_parameters_by_name()))
            c = layout.cell(layout.add_pcell_variant(local_pid,values))
            for k,v in c0.properties().items(): c.set_property(k,v)
            replaced.add(i.cell_index);i.cell_index=c.cell_index();i.dcplx_trans=pya.DCplxTrans()
        group_reports.append({'id':name,'span_um':span,'translation_x_um':dx,'sbend_count':len(variants)})
    for i in touched:
        selected_after[instance_key(i)] += 1
    removed = []
    for index in replaced:
        cell = layout.cell(index)
        if cell is not None and not any(True for _ in cell.each_parent_inst()):
            removed.append(cell.name);layout.delete_cell(index)
    for _ in range(5):
        orphan = [c for c in layout.top_cells() if c.name not in old_names]
        if not orphan: break
        removed.extend(c.name for c in orphan);layout.delete_cells([c.cell_index() for c in orphan])
    opts = pya.SaveLayoutOptions();opts.write_context_info=True
    try:
        layout.write(str(candidate),opts)
        reread = read(candidate,wg); source_layout = read(source,wg)
        after = reread.cell(root.name)
        require(after is not None and reread.dbu == layout.dbu,'Read-back cell or DBU mismatch')
        whole = instances(after)
        require(all(whole[k] >= v for k,v in selected_after.items()),'Changed instance missing on read-back')
        require(whole-selected_after == all_before-selected_before,'Unselected instances changed')
        require(shapes(reread,after) == original_shapes,'Parent direct shapes changed')
        changed_cells = unchanged_cells(source_layout,reread,removed+[root.name])
        require(not changed_cells,'Other cells changed: %s' % changed_cells[:20])
        require(sorted(c.name for c in reread.top_cells()) == sorted(c.name for c in source_layout.top_cells()),
                'Unexpected top-level cell')
        actual_radii = []
        for group in job['groups']:
            for i in select(after,group['sbends']):
                p = i.cell.pcell_parameters_by_name()
                require(abs(p['length']-span) < 1e-9,'Wrong re-read S-bend span')
                if abs(p['height']) > 1e-12:
                    actual_radii.append(p['Bezier_Rmin'])
                    require(p['Bezier_Rmin'] > limit,'Re-read radius constraint failed')
        checks = optical_checks(reread,after,tuple(job.get('si_layer',[1,0])),tuple(job.get('pin_layer',[1,10])))
        require(checks['passed'],'Optical checks failed: %s' % json.dumps(checks))
        report = {'passed':True,'input_file':str(source),'output_file':str(output),
                  'groups':group_reports,'minimum_radius_um':min(actual_radii) if actual_radii else None,
                  'radius_limit_um':limit,'checks':checks,'removed_target_cells':removed}
        os.replace(str(candidate),str(output))
        if report_path is not None:
            report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        return report
    except Exception:
        if candidate.exists(): candidate.unlink()
        raise


if __name__ == '__main__' or 'job_file' in globals():
    try:
        require('job_file' in globals(),'Run through KLayout with -rd job_file=<job.json>')
        job = json.loads(Path(str(job_file)).read_text(encoding='utf-8-sig'))
        result = run(job)
        print(json.dumps({'passed':True,'output':result['output_file'],
                          'minimum_radius_um':result['minimum_radius_um'],'groups':result['groups']}))
    except Exception:
        traceback.print_exc()
        raise
