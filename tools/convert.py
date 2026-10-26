"""Convert eCFR Part XML into per-subpart JSON for the OSHA Reader.

Usage: python3 -I convert.py <raw_dir> <out_dir> <as_of_date>
"""
import json, re, sys, html, os
import xml.etree.ElementTree as ET

RAW, OUT, ASOF = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.join(OUT, 'data', 's'), exist_ok=True)

ROMAN = {'i','ii','iii','iv','v','vi','vii','viii','ix','x','xi','xii','xiii','xiv','xv','xvi','xvii','xviii','xix','xx','xxi','xxii','xxiii','xxiv','xxv'}
INLINE_E = {'01': 'b', '02': 'b', '03': 'i', '04': 'b', '7333': 'i', '8064': 'i', '15': 'i', '51': 'sup', '52': 'sub', '54': 'sub'}
SKIP = {'HEAD', 'FTREF'}


def esc(t):
    return html.escape(t or '', quote=False)


def inline(el):
    """Render an element's mixed content (text + inline children) as safe HTML."""
    out = [esc(el.text)]
    for c in el:
        tag = c.tag
        if tag in ('I', 'em'):
            out.append('<i>' + inline(c) + '</i>')
        elif tag in ('strong', 'B'):
            out.append('<b>' + inline(c) + '</b>')
        elif tag == 'E':
            t = INLINE_E.get(c.get('T'), 'i')
            out.append(f'<{t}>' + inline(c) + f'</{t}>')
        elif tag in ('sup', 'SU'):
            out.append('<sup>' + inline(c) + '</sup>')
        elif tag == 'sub':
            out.append('<sub>' + inline(c) + '</sub>')
        elif tag == 'br':
            out.append('<br>')
        elif tag == 'img':
            src = c.get('src') or ''
            if src.startswith('/'):
                out.append(f'<a class="fig" href="https://www.ecfr.gov{esc(src)}" target="_blank" rel="noopener">View figure on eCFR</a>')
        elif tag == 'FTREF':
            out.append('<sup>' + inline(c) + '</sup>')
        else:
            out.append(inline(c))
        out.append(esc(c.tail))
    return ''.join(out)


def plain(el):
    return re.sub(r'\s+', ' ', ''.join(el.itertext())).strip()


ROMAN_SEQ = ['i','ii','iii','iv','v','vi','vii','viii','ix','x','xi','xii','xiii','xiv','xv','xvi','xvii','xviii','xix','xx','xxi','xxii','xxiii','xxiv','xxv']


class ParaTracker:
    """Track paragraph designations like (a)(1)(i)(A)(1) from leading markers.

    Levels: 0 letter, 1 number, 2 roman, 3 capital, 4 italic number, 5 italic roman.
    """
    def __init__(self):
        self.stack = []
        self.next_marker = None

    def _top(self, level):
        return next((mm for lv, mm in reversed(self.stack) if lv == level), None)

    def push(self, m, italic, digit_follows):
        top = self.stack[-1] if self.stack else None
        if m.isdigit():
            if italic:
                k = 4
            elif top and top[0] == 3 and m == '1':
                k = 4
            elif top and top[0] == 4 and top[1].isdigit() and int(m) == int(top[1]) + 1:
                k = 4
            else:
                k = 1
        elif m.isupper():
            k = 3
        elif m not in ROMAN:
            k = 6 if italic else 0
        elif italic:
            k = 6 if (top and top[0] == 6 and len(m) == 1 and top[1] and ord(m) == ord(top[1][-1]) + 1) else 5
        else:
            letter_prev = self._top(0)
            roman_prev = self._top(2)
            expected_letter = bool(letter_prev) and len(m) == 1 and ord(m) == ord(letter_prev[-1]) + 1
            roman_cont = (m == 'i') or (roman_prev in ROMAN_SEQ and ROMAN_SEQ.index(roman_prev) + 1 < len(ROMAN_SEQ)
                                        and ROMAN_SEQ[ROMAN_SEQ.index(roman_prev) + 1] == m)
            if not expected_letter:
                k = 2
            elif digit_follows:
                k = 0
            elif m != 'i' and roman_cont:
                k = 2
            else:
                idx = ROMAN_SEQ.index(m)
                k = 2 if self.next_marker == ROMAN_SEQ[idx + 1] else 0
        while self.stack and self.stack[-1][0] >= k:
            self.stack.pop()
        self.stack.append((k, m))
        return ''.join(f'({mm})' for _, mm in self.stack)


LEAD = re.compile(r'^\s*\(([a-zA-Z]{1,5}|\d{1,3})\)\s*')
HEADING = re.compile(r'^([^()]{1,100}?[.\u2014:])\s*(?=\()')


def first_marker(el):
    m = LEAD.match(''.join(el.itertext())) if el is not None else None
    return m.group(1) if m else None


def para_id(p_el, tracker):
    """Read the run of leading (x)(y) markers (with short headings between) from a <P>."""
    s = ''.join(p_el.itertext())
    italic_first = bool(len(p_el) and p_el[0].tag == 'I' and (
        (not (p_el.text or '').strip() and LEAD.match(p_el[0].text or ''))
        or ((p_el.text or '').strip() == '(' and re.fullmatch(r'[a-zA-Z0-9]{1,5}', (p_el[0].text or '').strip()))))
    des = ''
    first = True
    while True:
        m = LEAD.match(s)
        if not m:
            break
        rest = s[m.end():]
        h = HEADING.match(rest)
        after = rest[h.end():] if h else rest
        m2 = LEAD.match(rest) or (LEAD.match(after) if h else None)
        digit_follows = bool(m2 and m2.group(1).isdigit())
        des = tracker.push(m.group(1), italic_first and first, digit_follows)
        first = False
        if LEAD.match(rest):
            s = rest
            continue
        if h and LEAD.match(after):
            s = after
            continue
        break
    return des


def table_html(t):
    rows = []
    cap = t.find('CAPTION')
    if cap is not None:
        rows.append(f'<caption>{inline(cap)}</caption>')
    for part in ('THEAD', 'TBODY', 'TFOOT'):
        sec = t.find(part)
        if sec is None:
            continue
        rows.append(f'<{part.lower()}>')
        for tr in sec.findall('TR'):
            cells = []
            for c in tr:
                if c.tag not in ('TH', 'TD'):
                    continue
                span = ''
                if c.get('colspan'):
                    span += f' colspan="{int(c.get("colspan"))}"'
                if c.get('rowspan'):
                    span += f' rowspan="{int(c.get("rowspan"))}"'
                tag = c.tag.lower()
                cells.append(f'<{tag}{span}>{inline(c)}</{tag}>')
            rows.append('<tr>' + ''.join(cells) + '</tr>')
        rows.append(f'</{part.lower()}>')
    return '<div class="tw"><table>' + ''.join(rows) + '</table></div>'


def block(el, tracker, out, texts, sec_num):
    tag = el.tag
    if tag in SKIP:
        return
    if tag == 'P' or tag in ('FP', 'FP-1', 'FP-2', 'FP1-2', 'FP-DASH', 'P-2', 'FL-2', 'LDRWK'):
        des = para_id(el, tracker) if tag == 'P' else ''
        body = inline(el)
        if not body.strip():
            return
        attr = ''
        if des:
            pid = 'p' + re.sub(r'[()]+', '-', des).strip('-')
            seen = tracker.__dict__.setdefault('ids', {})
            if pid in seen:
                seen[pid] += 1
                pid = f'{pid}_{seen[pid]}'
            else:
                seen[pid] = 0
            attr = f' id="{pid}" data-p="{esc(des)}"'
        cls = '' if tag == 'P' else ' class="fp"'
        out.append(f'<p{attr}{cls}>{body}</p>')
        texts.append((des, plain(el)))
    elif tag in ('HD1', 'HD2', 'HD3', 'HED', 'TCAP', 'BCAP'):
        lvl = {'HD1': 'h3', 'HD2': 'h4', 'HD3': 'h5', 'HED': 'h5'}.get(tag, 'h5')
        txt = inline(el)
        if txt.strip():
            out.append(f'<{lvl}>{txt}</{lvl}>')
            if tag == 'HD1' and re.match(r'\s*Appendix', plain(el), re.I):
                tracker.stack = []
            texts.append(('', plain(el)))
    elif tag == 'NOTE':
        inner = []
        block_children(el, tracker, inner, texts, sec_num)
        out.append('<div class="note">' + ''.join(inner) + '</div>')
    elif tag == 'EXTRACT' or tag == 'EXAMPLE':
        inner = []
        block_children(el, tracker, inner, texts, sec_num)
        out.append('<div class="extract">' + ''.join(inner) + '</div>')
    elif tag == 'TABLE':
        out.append(table_html(el))
        texts.append(('', plain(el)))
    elif tag in ('DIV',):
        block_children(el, tracker, out, texts, sec_num)
    elif tag in ('CITA', 'SOURCE', 'AUTH', 'EDNOTE', 'APPRO'):
        t = plain(el)
        if t:
            out.append(f'<p class="cita">{esc(t)}</p>')
    elif tag == 'FTNT':
        inner = []
        block_children(el, tracker, inner, texts, sec_num)
        out.append('<div class="ftnt">' + ''.join(inner) + '</div>')
    elif tag == 'img':
        out.append('<p>' + inline(ET.fromstring(f'<x>{ET.tostring(el, encoding="unicode")}</x>')) + '</p>')
    elif tag in ('PSPACE', 'MATH', 'LDRFIG', 'AC', 'FR', 'GPH'):
        t = inline(el)
        if t.strip():
            out.append(f'<p class="fp">{t}</p>')
            texts.append(('', plain(el)))
    else:
        block_children(el, tracker, out, texts, sec_num)


def block_children(el, tracker, out, texts, sec_num):
    kids = list(el)
    for i, c in enumerate(kids):
        nxt = next((k for k in kids[i + 1:] if k.tag == 'P'), None)
        tracker.next_marker = first_marker(nxt)
        block(c, tracker, out, texts, sec_num)


def section_record(div, part, subpart, kind):
    head = plain(div.find('HEAD')) if div.find('HEAD') is not None else div.get('N')
    n = div.get('N')
    if kind == 'section':
        num = n.replace(part + '.', '', 1)
        title = re.sub(r'^§+\s*[\d.\-–]+\s*', '', head).rstrip('.')
        title = re.sub(r'^\d+\.\d+[\-–]\d+\.\d+\s*', '', title)
        sid = n
    else:
        num = ''
        title = head
        sid = part + '-' + re.sub(r'[^A-Za-z0-9]+', '-', n).strip('-')
    tracker = ParaTracker()
    out, texts = [], []
    block_children(div, tracker, out, texts, n)
    reserved = '[Reserved]' in head or (not texts)
    return {
        'id': sid, 'part': part, 'num': num, 'cite': (n if kind == 'section' else head.split('—')[0].strip()),
        'title': title, 'subpart': subpart, 'reserved': reserved, 'appendix': kind != 'section',
        'html': ''.join(out), 'text': texts,
    }


def run(part):
    root = ET.parse(os.path.join(RAW, f'part-{part}.xml')).getroot()
    part_title = plain(root.find('HEAD'))
    subparts = []
    for sp in root:
        if sp.tag == 'DIV6':
            sp_head = plain(sp.find('HEAD'))
            recs = []
            for el in sp.iter():
                if el.tag == 'DIV8':
                    recs.append(section_record(el, part, sp_head, 'section'))
                elif el.tag == 'DIV9':
                    recs.append(section_record(el, part, sp_head, 'appendix'))
            subparts.append({'code': sp.get('N'), 'title': sp_head, 'sections': recs})
        elif sp.tag in ('DIV8', 'DIV9') and subparts:
            # sections that follow a subpart heading at part level belong to that subpart
            last = subparts[-1]
            if sp.get('N', '').startswith(part + '.901'):
                last = next(x for x in subparts if x['code'] == 'V-Y')
            last['sections'].append(section_record(sp, part, last['title'], 'section' if sp.tag == 'DIV8' else 'appendix'))
    return part_title, subparts


index = {'asOf': ASOF, 'parts': []}
search = []
for part in ('1910', '1904'):
    ptitle, sps = run(part)
    pentry = {'part': part, 'title': ptitle, 'subparts': []}
    for sp in sps:
        for sec in sp['sections']:
            sec['file'] = 'data/s/' + re.sub(r'[^A-Za-z0-9.\-]+', '-', sec['id']) + '.json'
            with open(os.path.join(OUT, sec['file']), 'w', encoding='utf-8') as f:
                json.dump({k: sec[k] for k in ('id', 'cite', 'title', 'html', 'appendix')}, f, ensure_ascii=False, separators=(',', ':'))
        pentry['subparts'].append({
            'code': sp['code'], 'title': sp['title'],
            'sections': [{'id': s['id'], 'cite': s['cite'], 'num': s['num'], 'title': s['title'], 'file': s['file'],
                          'reserved': s['reserved'], 'appendix': s['appendix']} for s in sp['sections']],
        })
        for s in sp['sections']:
            if s['reserved']:
                continue
            for des, t in s['text']:
                if t:
                    search.append([s['id'], des, t])
    index['parts'].append(pentry)

with open(os.path.join(OUT, 'data', 'index.json'), 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(OUT, 'data', 'search.json'), 'w', encoding='utf-8') as f:
    json.dump(search, f, ensure_ascii=False, separators=(',', ':'))
print('ok')
