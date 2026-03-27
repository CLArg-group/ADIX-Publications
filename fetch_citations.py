#!/usr/bin/env python3
"""
fetch_citations.py — Update papers.json with citation data from Semantic Scholar.

Uses the batch API to fetch all papers with DOIs in one request.
Papers without DOIs are looked up individually by title.

Stores:
  - citationCount: total citation count (displayed per paper)
  - citationsPerYear: {year: count} (used for aggregate chart)

Usage:
    python fetch_citations.py

Requires Python 3.6+, no external dependencies.
Run every few months to refresh. Commit the updated papers.json afterwards.
"""

import json, time, re, sys
from urllib.request import urlopen, Request
from urllib.parse import quote, urlencode
from urllib.error import HTTPError

PAPERS_FILE = 'papers.json'
API         = 'https://api.semanticscholar.org/graph/v1'
BATCH_FIELDS = 'citationCount,citations.year,title,year'
SEARCH_FIELDS = 'citationCount,citations.year,title,year'


def fetch_json(url, post_data=None, retries=3):
    for attempt in range(retries):
        try:
            if post_data is not None:
                body = json.dumps(post_data).encode('utf-8')
                req = Request(url, data=body, headers={
                    'User-Agent': 'ADIX-publications/1.0',
                    'Content-Type': 'application/json'
                })
            else:
                req = Request(url, headers={'User-Agent': 'ADIX-publications/1.0'})
            with urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f'  [rate limited, waiting {wait}s]', flush=True)
                time.sleep(wait)
            elif e.code == 404:
                return None
            else:
                return None
        except Exception:
            return None
    return None


def arxiv_id_from_doi(doi):
    m = re.search(r'arxiv\.(\d{4}\.\d+)', doi, re.IGNORECASE)
    return m.group(1) if m else None


def s2_id(paper):
    doi = (paper.get('doi') or '').strip()
    if not doi:
        return None
    arxiv_id = arxiv_id_from_doi(doi)
    return f'ARXIV:{arxiv_id}' if arxiv_id else f'DOI:{doi}'


def citations_per_year(result):
    """Compute {year: count} from citations array."""
    if not result or 'citations' not in result:
        return None
    years = {}
    for c in result.get('citations', []):
        y = c.get('year')
        if y is not None:
            years[str(y)] = years.get(str(y), 0) + 1
    return dict(sorted(years.items())) if years else None


def search_by_title(title, year):
    params = urlencode({'query': title, 'fields': SEARCH_FIELDS, 'limit': '5'})
    r = fetch_json(f'{API}/paper/search?{params}')
    if not r or 'data' not in r:
        return None
    for p in r['data']:
        if p.get('year') == year:
            return p
    return None


def apply_result(paper, result):
    if not result or result.get('citationCount') is None:
        return False
    paper['citationCount'] = result['citationCount']
    cpy = citations_per_year(result)
    if cpy:
        paper['citationsPerYear'] = {k: v for k, v in cpy.items() if v > 0}
    else:
        paper.pop('citationsPerYear', None)
    return True


def main():
    with open(PAPERS_FILE, encoding='utf-8') as f:
        papers = json.load(f)

    total = len(papers)

    # Step 1: Batch lookup
    batch_ids = []
    batch_map = {}
    no_id = []

    for i, p in enumerate(papers):
        sid = s2_id(p)
        if sid:
            batch_map[len(batch_ids)] = i
            batch_ids.append(sid)
        else:
            no_id.append(i)

    print(f'{len(batch_ids)} papers with DOI/arXiv ID, {len(no_id)} without.')
    print('Fetching batch from Semantic Scholar...', flush=True)

    batch_result = fetch_json(
        f'{API}/paper/batch?fields={BATCH_FIELDS}',
        post_data={'ids': batch_ids}
    )

    n_found = 0
    fallback = list(no_id)

    if batch_result:
        print(f'Batch returned {len(batch_result)} results.\n')
        for bi, result in enumerate(batch_result):
            pi = batch_map[bi]
            p = papers[pi]
            label = (p['title'][:58] + '...') if len(p['title']) > 58 else p['title']
            if apply_result(p, result):
                n_found += 1
                print(f'  OK [{pi+1:3}] {p["citationCount"]:4} cited  {label}')
            else:
                fallback.append(pi)
                print(f'  -- [{pi+1:3}]          {label}')
    else:
        print('Batch request failed — falling back to individual lookups.')
        fallback = list(range(total))

    # Step 2: Title search for remaining (skip with --batch-only)
    batch_only = '--batch-only' in sys.argv
    if fallback and not batch_only:
        print(f'\nSearching {len(fallback)} remaining papers by title...')
        for pi in fallback:
            p = papers[pi]
            label = (p['title'][:58] + '...') if len(p['title']) > 58 else p['title']
            print(f'  [{pi+1:3}] {label}', end='', flush=True)

            result = search_by_title(p['title'], p.get('year'))
            time.sleep(3)

            if apply_result(p, result):
                n_found += 1
                print(f'  OK  ({p["citationCount"]})')
            else:
                p.pop('citationCount', None)
                p.pop('citationsPerYear', None)
                print('  --')

    # Write back
    with open(PAPERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)
        f.write('\n')

    total_cites = sum(p.get('citationCount', 0) for p in papers)
    print(f'\nDone: {n_found}/{total} papers found. Total citations: {total_cites}')


if __name__ == '__main__':
    main()
