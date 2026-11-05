"""Compact one ordered pad row using existing KLayout Paths and pad instances.

Import in full KLayout after the caller loads the required PDK/PCells. All lengths
are integer DBU. This module never loads/saves layouts, changes editor settings,
or edits fixed electrodes. The caller selects cells in the SAME coordinate frame,
runs native PDK DRC and validates protected geometry before publishing a version.
"""
import math
import pya


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _region(layout, cell, info):
    result = pya.Region()
    for li in layout.layer_indices():
        layer = layout.get_info(li)
        if (layer.layer, layer.datatype) == tuple(info):
            result += pya.Region(cell.begin_shapes_rec(li))
    return result.merged()


def _length(points):
    return sum(math.hypot(a.x-b.x, a.y-b.y) for a, b in zip(points, points[1:]))


def _clean(points):
    result = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result


def collect_routes(layout, metal_cell, pad_cell, *, wire_width, expected_count,
                   metal_info=(12, 0), id_property=125, net_ids=None,
                   escape_index=1, fixed_lengths=None, direction=1):
    """Bind selected direct Paths to a single row of rectangular M2 pad instances.

    Both containers must use the same local axes/origin. Pad instances may have
    transforms; regular arrays, shared pads and ambiguous/duplicate IDs are rejected.
    Each Path must end vertically INSIDE its pad; its first point is a preserved
    20-um landing (or the caller's width), not necessarily the fixed electrode.
    fixed_lengths optionally maps IDs to unchanged neck/taper centreline lengths.
    direction=+1 routes toward increasing Y; -1 supports a lower/mirrored bank.
    """
    _require(direction in (-1, 1), 'direction must be +1 or -1')
    _require(wire_width > 0 and expected_count > 0, 'positive width/count required')
    wanted = set(net_ids) if net_ids is not None else None
    pads = []
    for inst in pad_cell.each_inst():
        _require(len(list(inst.cell_inst.each_cplx_trans())) == 1,
                 'Select individual pad instances, not regular arrays')
        region = _region(layout, inst.cell, metal_info).transformed(inst.cplx_trans)
        box = region.bbox()
        _require(not region.is_empty() and (region ^ pya.Region(box)).is_empty(),
                 'Each selected pad must have rectangular M2 geometry')
        pads.append((inst, region, box))
    routes = []
    seen = set()
    used = set()
    for li in layout.layer_indices():
        inf = layout.get_info(li)
        if (inf.layer, inf.datatype) != tuple(metal_info):
            continue
        for shape in metal_cell.shapes(li).each():
            if not shape.is_path() or shape.path.width != wire_width:
                continue
            name = shape.property(id_property)
            if wanted is not None and name not in wanted:
                continue
            _require(name is not None and str(name) != '' and str(name) not in seen,
                     'Selected Paths require unique, nonempty net properties')
            name = str(name)
            path = shape.path
            points = list(path.each_point())
            _require(path.bgn_ext == 0 and path.end_ext == 0 and not path.round,
                     'Extended or round-ended Paths require an explicit adapter')
            _require(len(points) >= 2 and 0 <= escape_index < len(points),
                     'Invalid Path or escape point index')
            _require(points[-2].x == points[-1].x and
                     direction*points[-1].y > direction*points[-2].y,
                     'Path must approach the pad vertically in the selected direction')
            tip = points[-1]
            matches = [(j, item) for j, item in enumerate(pads)
                       if item[2].contains(tip) and
                       (pya.Region(path.polygon()) & item[1]).area() > 0]
            _require(len(matches) == 1, 'Path endpoint must contact exactly one pad: '+name)
            j, (inst, region, box) = matches[0]
            _require(j not in used, 'Shared pad encountered; select independent nets only')
            _require(points[0].y == points[escape_index].y,
                     'Landing and chosen escape point must have the same Y')
            seen.add(name)
            used.add(j)
            routes.append(dict(id=name, shape=shape, old_path=path.to_s(),
                old_points=points, width=wire_width, escape_x=points[escape_index].x,
                pad_instance=inst, old_pad_transform=inst.cplx_trans.to_s(),
                pad_box=box, fixed_length=float((fixed_lengths or {}).get(name, 0))))
    _require(len(routes) == expected_count, 'Unexpected selected Path count')
    _require(wanted is None or seen == {str(n) for n in wanted}, 'Requested net IDs not found')
    routes.sort(key=lambda n: n['escape_x'])
    _require(all(a['escape_x'] < b['escape_x'] for a, b in zip(routes, routes[1:])),
             'Escape columns must be strictly ordered')
    _require(all(a['pad_box'].center().x < b['pad_box'].center().x
                 for a, b in zip(routes, routes[1:])), 'Existing pad order differs from net order')
    _require(len({n['pad_box'].center().y for n in routes}) == 1, 'Select one pad row at a time')
    _require(len({(n['pad_box'].width(), n['pad_box'].height()) for n in routes}) == 1,
             'Selected row must use equal pad dimensions')
    return routes


def _isotonic(values):
    """Least-squares nondecreasing fit; does not claim globally shortest wiring."""
    blocks = []
    for value in values:
        blocks.append([float(value), 1])
        while len(blocks) > 1 and blocks[-2][0]/blocks[-2][1] > blocks[-1][0]/blocks[-1][1]:
            total, count = blocks.pop()
            blocks[-1][0] += total
            blocks[-1][1] += count
    return [total/count for total, count in blocks for _ in range(count)]


def plan_compaction(routes, *, fanout_y, pad_pitch, pad_margin, pad_overlap,
                    pad_right_limit=None, pad_left_limit=None, pad_center_y=None,
                    direction=1, require_lower=True):
    """Return an uncommitted plan of horizontal/vertical/45-degree Paths.

    Limits refer to pad METAL edges. fanout_y and pad_margin must be chosen from
    actual obstacles/PDK clearance; this planner has no knowledge of trenches.
    A fixed pad_center_y is supported but rejected if it cannot fit the fanout.
    require_lower means toward the devices (smaller oriented Y), for either bank.
    """
    _require(bool(routes) and direction in (-1, 1), 'Routes and valid direction required')
    _require(pad_margin >= 0 and pad_overlap > 0, 'Invalid pad margin/overlap')
    first = routes[0]['pad_box']
    _require(pad_pitch >= first.width(), 'Pitch cannot be smaller than pad width')
    _require(pad_overlap < first.height(), 'Overlap must terminate inside pad metal')
    center = first.center()
    left = center.x-first.left
    right = first.right-center.x
    lower = -math.inf if pad_left_limit is None else pad_left_limit+left
    upper = math.inf if pad_right_limit is None else pad_right_limit-right-(len(routes)-1)*pad_pitch
    _require(lower <= upper, 'Pad row cannot fit between requested metal-edge limits')
    fitted = _isotonic([n['escape_x']-i*pad_pitch for i, n in enumerate(routes)])
    xs = [round(min(upper, max(lower, z)))+i*pad_pitch for i, z in enumerate(fitted)]
    base = direction*fanout_y
    _require(all(base >= direction*n['old_points'][0].y for n in routes),
             'Fanout baseline crosses the preserved landing')
    near_half = center.y-first.bottom if direction == 1 else first.top-center.y
    reach = max(base+abs(x-n['escape_x']) for x, n in zip(xs, routes))
    minimum_y = reach+near_half+pad_margin
    y = minimum_y if pad_center_y is None else direction*pad_center_y
    _require(y >= minimum_y, 'Requested pad Y cannot accommodate 45-degree routing')
    old_y = direction*center.y
    _require(not require_lower or y < old_y, 'Plan would not move pads toward the devices')
    entries = []
    old_total = new_total = 0.0
    for n, x in zip(routes, xs):
        start = n['old_points'][0]
        sx = n['escape_x']
        end_y = y-near_half+pad_overlap
        points = _clean([start, pya.Point(sx, start.y), pya.Point(sx, direction*base),
                        pya.Point(x, direction*(base+abs(x-sx))), pya.Point(x, direction*end_y)])
        _require(all(a.x == b.x or a.y == b.y or abs(a.x-b.x) == abs(a.y-b.y)
                     for a, b in zip(points, points[1:])), 'Non-diagonal segment')
        old_box = n['pad_box']
        old_near = min(direction*old_box.bottom, direction*old_box.top)
        tail = direction*n['old_points'][-1].y-old_near
        _require(0 <= tail <= old_box.height(), 'Old pad endpoint is outside metal')
        old_length = _length(n['old_points'])-tail+n['fixed_length']
        new_length = _length(points)-pad_overlap+n['fixed_length']
        old_total += old_length
        new_total += new_length
        new_center = pya.Point(x, direction*y)
        entries.append(dict(route=n, points=points, pad_center=new_center,
                            old_length=old_length, new_length=new_length))
    _require(old_total > 0, 'Old external centreline length must be positive')
    return dict(entries=entries, direction=direction,
                metrics=dict(net_count=len(entries), old_pad_y=center.y, new_pad_y=direction*y,
                pad_shift_toward_devices=old_y-y, old_total_length=old_total,
                new_total_length=new_total, reduction_percent=100*(old_total-new_total)/old_total,
                all_leads_shorter=all(e['new_length'] < e['old_length'] for e in entries),
                length_metric='centreline to first pad-metal edge, excluding metal inside pads'))


def apply_plan(plan):
    """Change only selected Path geometry and pad translations; preflight all first."""
    for entry in plan['entries']:
        n = entry['route']
        _require(n['shape'].path.to_s() == n['old_path'], 'Selected Path changed after planning')
        _require(n['pad_instance'].cplx_trans.to_s() == n['old_pad_transform'],
                 'Pad changed after planning')
    for entry in plan['entries']:
        n = entry['route']
        n['shape'].path = pya.Path(entry['points'], n['width'])
        delta = entry['pad_center']-n['pad_box'].center()
        n['pad_instance'].cplx_trans = pya.ICplxTrans(1, 0, False, delta.x, delta.y)*n['pad_instance'].cplx_trans


def check_pad_connections(layout, root, plan, *, metal_info=(12, 0), opening_info=(13, 0),
                          terminal_regions=None):
    """Check distinct start/terminal-to-pad nets in the supplied COMMON root frame.

    This supplements, not replaces, full M1 heater analysis and native PDK DRC.
    Optional terminal_regions maps net IDs to actual electrode regions.
    """
    m2 = _region(layout, root, metal_info)
    components = [pya.Region(p) for p in m2.each()]
    openings = [pya.Region(p) for p in _region(layout, root, opening_info).each()]
    _require((_region(layout, root, opening_info)-m2).is_empty(), 'Uncovered pad opening')
    used = set()
    mapping = []
    for entry in plan['entries']:
        n = entry['route']
        seed = (terminal_regions or {}).get(n['id'])
        if seed is None:
            p = entry['points'][0]
            seed = pya.Region(pya.Box(p.x-1, p.y-1, p.x+1, p.y+1))
        hits = [i for i, c in enumerate(components) if (c & seed).area() > 0]
        _require(len(hits) == 1 and hits[0] not in used, 'Open, ambiguous or shorted selected net')
        idx = hits[0]
        component = components[idx]
        old_box = n['pad_box']
        box = old_box.transformed(pya.Trans(entry['pad_center']-old_box.center()))
        _require((pya.Region(box)-component).is_empty(), 'Net misses its designated pad')
        _require(sum((component & op).area() > 0 for op in openings) == 1,
                 'Selected net must connect exactly one pad opening')
        used.add(idx)
        mapping.append(dict(id=n['id'], component=idx))
    return dict(checked_nets=len(mapping), open_or_shorted_selected_nets=0,
                openings_covered=True, mapping=mapping)
