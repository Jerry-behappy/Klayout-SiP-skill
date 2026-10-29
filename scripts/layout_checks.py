"""Native KLayout checks shared by layout-editing scripts (no file hashes)."""
from collections import Counter
import math
import pya


def instance_key(i):
    return (i.cell.name, str(i.cplx_trans), i.na, i.nb, str(i.a), str(i.b),
            str(sorted(i.properties().items(), key=lambda a: str(a[0]))))


def instances(cell):
    return Counter(instance_key(i) for i in cell.each_inst())


def shapes(layout, cell):
    return {layout.get_info(li).to_s(): Counter(str(s) for s in cell.shapes(li).each())
            for li in layout.layer_indices() if not cell.shapes(li).is_empty()}


def unchanged_cells(before, after, excluded_names=()):
    """Compare direct shapes and instance multisets, preserving duplicate instances."""
    excluded = set(excluded_names)
    failures = []
    for old in before.each_cell():
        if old.name in excluded:
            continue
        new = after.cell(old.name)
        if new is None or instances(old) != instances(new) or shapes(before, old) != shapes(after, new):
            failures.append(old.name)
    return failures


def optical_checks(layout, root, si_info=(1, 0), pin_info=(1, 10), tolerance_dbu=25):
    """Check PinRec matches, actual Si continuity and unintended Si intersections.

    These are geometric/connectivity checks, not a replacement for foundry DRC.
    Electrical pins on a separate layer are deliberately excluded.
    """
    si = layout.find_layer(*si_info)
    pin = layout.find_layer(*pin_info)
    if si is None or pin is None:
        raise ValueError('Missing Si or optical PinRec layer')
    parts = []

    def walk(cell, tr, chain):
        pp = []
        for s in cell.shapes(pin).each():
            if s.is_path():
                path = s.path.transformed(tr)
                points = list(path.each_point())
                v = points[-1] - points[0]
                pp.append({'xy': (path.bbox().center().x, path.bbox().center().y),
                           'v': (v.x, v.y), 'width': path.width})
        if pp:
            parts.append({'id': len(parts), 'chain': chain, 'pins': pp,
                          'si': pya.Region(cell.begin_shapes_rec(si)).transformed(tr)})
        for j, i in enumerate(cell.each_inst()):
            for it in i.cell_inst.each_cplx_trans():
                walk(i.cell, tr * it, chain + '/' + str(j) + ':' + i.cell.name)

    walk(root, pya.ICplxTrans(), root.name)
    pins = [dict(p, part=a['id']) for a in parts for p in a['pins']]
    unmatched, ambiguous, continuity, overlaps = [], [], [], []
    seen, connections = set(), []
    for p in pins:
        near = [q for q in pins if p['part'] != q['part'] and p['width'] == q['width']
                and p['v'][0] * q['v'][0] + p['v'][1] * q['v'][1] < 0
                and math.dist(p['xy'], q['xy']) <= tolerance_dbu]
        if not near:
            unmatched.append(p)
        elif len(near) != 1:
            ambiguous.append(p)
        else:
            q = near[0]
            pair = tuple(sorted(((p['part'], p['xy']), (q['part'], q['xy']))))
            if pair not in seen:
                seen.add(pair)
                connections.append((p, q))
    for p, q in connections:
        x, y = p['xy']; u, v = q['xy']
        half = min(p['width'], q['width']) // 2 - 2
        if half <= 0:
            raise ValueError('Port width too small for this continuity check')
        box = (pya.Box(min(x, u)-5, min(y, v)-half, max(x, u)+5, max(y, v)+half)
               if p['v'][0] else
               pya.Box(min(x, u)-half, min(y, v)-5, max(x, u)+half, max(y, v)+5))
        missing = pya.Region(box) - (parts[p['part']]['si'] | parts[q['part']]['si'])
        if missing.area() > 4:
            continuity.append({'a': parts[p['part']]['chain'], 'b': parts[q['part']]['chain'],
                               'bbox_dbu': str(missing.bbox())})
    for j, a in enumerate(parts):
        for b in parts[j+1:]:
            if not a['si'].bbox().overlaps(b['si'].bbox()):
                continue
            hit = a['si'] & b['si']
            if hit.is_empty():
                continue
            mask = pya.Region()
            # Exempt only this pair's coincident port faces.
            for p in a['pins']:
                for q in b['pins']:
                    if math.dist(p['xy'], q['xy']) <= tolerance_dbu:
                        x, y = p['xy']; r = max(p['width'], q['width']) // 2 + 50
                        mask.insert(pya.Box(x-r, y-r, x+r, y+r))
            bad = hit - mask
            if bad.area() > 4:
                overlaps.append({'a': a['chain'], 'b': b['chain'],
                                 'bbox_dbu': str(bad.bbox()), 'area_dbu2': bad.area()})
    return {'passed': not (unmatched or ambiguous or continuity or overlaps),
            'pin_count': len(pins), 'connection_count': len(connections),
            'unmatched': unmatched, 'ambiguous': ambiguous,
            'continuity_failures': continuity, 'intersections': overlaps}
