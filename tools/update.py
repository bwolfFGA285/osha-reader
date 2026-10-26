"""Weekly refresh for the OSHA General Industry Reader (run by GitHub Actions).

1. Downloads the current text of 29 CFR Parts 1910 and 1904 from eCFR and
   rebuilds data/index.json, data/search.json and data/s/*.json.
2. Checks the Federal Register for new OSHA notices on Parts 1910/1904 that
   are not yet listed in data/news.json and writes them to
   tools/new-notices.md, so the workflow can open a GitHub issue for review.

Uses only the Python standard library.
"""
import gzip, io, json, os, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
UA = {'User-Agent': 'osha-general-industry-reader (GitHub Actions)', 'Accept-Encoding': 'gzip'}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
        return raw


def refresh_text():
    titles = json.loads(get('https://www.ecfr.gov/api/versioner/v1/titles.json'))['titles']
    t29 = next(t for t in titles if t['number'] == 29)
    as_of = t29['up_to_date_as_of']
    current = json.load(open(os.path.join(DATA, 'index.json'))).get('asOf')
    if current == as_of and '--force' not in sys.argv:
        print(f'Text already current as of {as_of}')
        return False
    tmp = tempfile.mkdtemp()
    raw, out = os.path.join(tmp, 'raw'), os.path.join(tmp, 'out')
    os.makedirs(raw)
    for part in ('1910', '1904'):
        url = f'https://www.ecfr.gov/api/versioner/v1/full/{as_of}/title-29.xml?part={part}'
        with open(os.path.join(raw, f'part-{part}.xml'), 'wb') as f:
            f.write(get(url))
    subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'tools', 'convert.py'), raw, out, as_of], check=True)
    # replace generated files only; keep news.json and summaries.json
    shutil.rmtree(os.path.join(DATA, 's'), ignore_errors=True)
    shutil.copytree(os.path.join(out, 'data', 's'), os.path.join(DATA, 's'))
    for f in ('index.json', 'search.json'):
        shutil.copy(os.path.join(out, 'data', f), os.path.join(DATA, f))
    news_path = os.path.join(DATA, 'news.json')
    news = json.load(open(news_path, encoding='utf-8'))
    news['textAsOf'] = as_of
    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
    print(f'Regulation text updated to {as_of}')
    return True


def check_notices():
    news = json.load(open(os.path.join(DATA, 'news.json'), encoding='utf-8'))
    known = {n['url'] for it in news['items'] for n in it['notices']}
    since = max(n['date'] for it in news['items'] for n in it['notices'])
    found = {}
    for part in ('1910', '1904'):
        q = [('per_page', '100'), ('order', 'newest'),
             ('conditions[agencies][]', 'occupational-safety-and-health-administration'),
             ('conditions[cfr][title]', '29'), ('conditions[cfr][part]', part),
             ('conditions[publication_date][gte]', since)]
        for fld in ('title', 'type', 'publication_date', 'html_url', 'action', 'abstract', 'dates'):
            q.append(('fields[]', fld))
        url = 'https://www.federalregister.gov/api/v1/documents.json?' + urllib.parse.urlencode(q)
        for d in json.loads(get(url)).get('results', []):
            if d['html_url'] not in known:
                found[d['html_url']] = d
    path = os.path.join(ROOT, 'tools', 'new-notices.md')
    if not found:
        if os.path.exists(path):
            os.remove(path)
        print('No new Federal Register notices')
        return
    lines = ['New OSHA Federal Register notices for Part 1910 / 1904 that are not in What\'s New yet.',
             'Add each one to data/news.json (or note that it does not matter), then close this issue.', '']
    for d in sorted(found.values(), key=lambda x: x['publication_date'], reverse=True):
        lines += [f"### {d['title']}",
                  f"- Published: {d['publication_date']} · Type: {d['type']} · {d.get('action') or ''}",
                  f"- Link: {d['html_url']}",
                  f"- Dates: {d.get('dates') or 'n/a'}",
                  f"- Summary: {d.get('abstract') or 'n/a'}", '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'{len(found)} new notice(s) written to tools/new-notices.md')


if __name__ == '__main__':
    refresh_text()
    check_notices()
