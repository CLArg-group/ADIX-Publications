#!/usr/bin/env python3
"""
fetch_citations.py — Update papers.json with per-year citation data from Semantic Scholar.

Usage:
    python fetch_citations.py

Requires Python 3.6+, no external dependencies.
Run every few months to refresh citation counts. The updated papers.json
can then be committed directly to the repository.
"""

import json, time, re
from urllib.request import urlopen, Request
from urllib.parse import quote, urlencode
from urllib.error import HTTPError

PAPERS_FILE = 'papers.json'
API         = 'https://api.semanticscholar.org/graph/v1'
FIELDS      = 'citationsPerYear,title,year'
DELAY       = 1.5   # seconds between requests (S2 free tier: ~1 req/sec)


def fetch(url, retries=3):
    req = Request(url, headers={'User-Agent': 'ADIX-publications/1.0'})
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f' [rate limited, waiting {wait}s…]', end='', flush=True)
                time.sleep(wait)
            elif e.code == 404:
                return None
            else:
                return None
        except Exception:
            return None
    return None


def by_doi(doi):
    r = fetch(f'{API}/paper/DOI:{quote(doi, safe="")}?fields={FIELDS}')
    return r if r and 'paperId' in r else None


def by_arxiv(arxiv_id):
    r = fetch(f'{API}/paper/ARXIV:{arxiv_id}?fields={FIELDS}')
    return r if r and 'paperId' in r else None


def by_title(title, year):
    params = urlencode({'query': title, 'fields': FIELDS, 'limit': '5'})
    r = fetch(f'{API}/paper/search?{params}')
    if not r or 'data' not in r:
        return None
    for p in r['data']:
        if p.get('year') == year:
            return p
    return None


def arxiv_id_from_doi(doi):
    """Extract arXiv ID from DOIs like 10.48550/ARXIV.2505.15742."""
    m = re.search(r'arxiv\.(\d{4}\.\d+)', doi, re.IGNORECASE)
    return m.group(1) if m else None


def main():
    with open(PAPERS_FILE, encoding='utf-8') as f:
        papers = json.load(f)

    total   = len(papers)
    n_found = 0

    for i, p in enumerate(papers):
        label = (p['title'][:60] + '…') if len(p['title']) > 60 else p['title']
        print(f'[{i+1:3}/{total}] {label}', end='', flush=True)

        result = None
        doi = (p.get('doi') or '').strip()

        # 1. Try DOI (or arXiv ID extracted from DOI)
        if doi:
            arxiv_id = arxiv_id_from_doi(doi)
            result = by_arxiv(arxiv_id) if arxiv_id else by_doi(doi)
            time.sleep(DELAY)

        # 2. Fall back to title search
        if not result:
            result = by_title(p['title'], p.get('year'))
            time.sleep(DELAY)

        cpy = result.get('citationsPerYear') if result else None
        if cpy and any(v > 0 for v in cpy.values()):
            p['citationsPerYear'] = dict(sorted(
                {k: v for k, v in cpy.items() if v > 0}.items()
            ))
            n_found += 1
            total_cites = sum(p['citationsPerYear'].values())
            print(f'  ✓  {total_cites} citations', flush=True)
        else:
            p.pop('citationsPerYear', None)
            print('  —', flush=True)

    with open(PAPERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f'\nDone: citation data found for {n_found}/{total} papers.')
    print('Commit the updated papers.json to apply changes to the website.')


if __name__ == '__main__':
    main()
