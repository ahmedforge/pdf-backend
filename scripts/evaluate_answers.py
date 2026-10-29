"""Black-box SSE evaluation using synthetic PDFs; no access to user documents."""
import argparse
import json
import math
import re
import secrets
import statistics
import textwrap
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import httpx


def pdf_bytes(document):
    """Produce simple ASCII, selectable-text test PDFs without extra dependencies."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    page_refs=[]
    for index, page in enumerate(document['pages'], 1):
        lines=[document['title'], f'Page {index}: {page["heading"]}', '']
        lines.extend(textwrap.wrap(page['text'], 85))
        content=['BT /F1 12 Tf 50 760 Td 18 TL']
        for line in lines:
            escaped=line.replace('\\','\\\\').replace('(', '\\(').replace(')', '\\)')
            content.append(f'({escaped}) Tj T*')
        content.append('ET')
        stream='\n'.join(content).encode('ascii')
        page_id=len(objects)+1
        page_refs.append(f'{page_id} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id+1} 0 R >>'.encode())
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects[1]=f'<< /Type /Pages /Count {len(page_refs)} /Kids [{" ".join(page_refs)}] >>'.encode()
    data=bytearray(b'%PDF-1.4\n')
    offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data)); data.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(data)


def normalize(text):
    text=' '.join(unicodedata.normalize('NFKC',text).lower().split())
    for word,number in [('two','2'),('four','4'),('five','5'),('six','6'),('seven','7')]:
        text=re.sub(r'\b'+word+r'\b',number,text)
    return text


def contains(text, term):
    return bool(re.search(r'(?<!\w)'+re.escape(normalize(term))+r'(?!\w)',normalize(text)))


def score(case, answer, sources, complete):
    normalized=normalize(answer)
    markers=[int(n) for n in re.findall(r'[\[【]Chunk\s+(\d+)[\]】]',answer)]
    source_map={s['chunk_index']: s for s in sources}
    terms=case['expected_terms']
    correct=(all(contains(answer,t) for t in terms) if case['answerable']
             else any(p in normalized for p in ['could not find', 'not provided', 'not mentioned', 'does not provide', 'not specified', 'does not contain', 'not available', "doesn't provide"]))
    valid=[n for n in markers if n in source_map]
    supported=[n for n in valid if source_map[n].get('page')==case['expected_page']
               and all(contains(source_map[n].get('text',''),t) for t in terms)] if case['answerable'] else []
    return {'answer_match': bool(correct and complete), 'citation_markers': markers,
            'matched_markers': valid, 'supported_markers': supported,
            'citation_hit': bool(supported and complete) if case['answerable'] else None}


def percentile(values, fraction):
    return sorted(values)[max(0,math.ceil(len(values)*fraction)-1)] if values else None


def run(args):
    corpus=json.loads(args.corpus.read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]; created=[]
    email=f'eval-{secrets.token_hex(8)}@example.com'
    password=secrets.token_urlsafe(24)
    with httpx.Client(base_url=args.base_url.rstrip('/'),timeout=180) as client:
        client.post('/auth/register',json={'email':email,'password':password}).raise_for_status()
        login=client.post('/auth/login',json={'email':email,'password':password}); login.raise_for_status()
        client.headers['Authorization']='Bearer '+login.json()['access_token']
        try:
            for doc in corpus:
                data=pdf_bytes(doc)
                (args.output/f'{doc["slug"]}.pdf').write_bytes(data)
                upload=client.post('/upload',files={'file':(f'eval-{doc["slug"]}.pdf',data,'application/pdf')})
                upload.raise_for_status(); doc_id=upload.json()['document_id']; created.append(doc_id)
                for case in doc['cases']:
                    start=time.perf_counter(); answer=''; sources=[]; first=None; complete=False; error=None
                    try:
                        with client.stream('POST',f'/files/{doc_id}/ask/stream?format=sse',json={'question':case['question'],'top_k':5}) as response:
                            response.raise_for_status()
                            if 'text/event-stream' not in response.headers.get('content-type',''): raise ValueError('Non-SSE response')
                            event=''; parts=[]
                            for line in response.iter_lines():
                                if line.startswith('event:'): event=line[6:].strip()
                                elif line.startswith('data:'): parts.append(line[5:].lstrip())
                                elif not line and parts:
                                    payload=json.loads('\n'.join(parts)); parts=[]
                                    if event=='sources': sources=payload['sources']
                                    elif event=='token':
                                        if first is None: first=time.perf_counter()-start
                                        answer+=payload['text']
                                    elif event=='error': error=payload.get('message','SSE error')
                                    elif event=='done': complete=payload['complete']
                    except (httpx.HTTPError, ValueError, KeyError) as exc:
                        error=type(exc).__name__
                    row={'document':doc['slug'],**case,'answer':answer,'sources':sources,'complete':complete,'error':error,
                         'first_token_seconds':first,'total_seconds':time.perf_counter()-start}
                    row.update(score(case,answer,sources,complete and not error)); rows.append(row)
                    (args.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
                    print(f'{len(rows):02d}: match={row["answer_match"]} citation={row["citation_hit"]} complete={complete} {case["question"]}',flush=True)
                    time.sleep(args.interval)
        finally:
            for doc_id in created:
                response=client.delete(f'/files/{doc_id}')
                if response.status_code!=200: print(f'Evaluation cleanup failed for document {doc_id}: HTTP {response.status_code}',flush=True)
    positives=[r for r in rows if r['answerable']]; negatives=[r for r in rows if not r['answerable']]
    successful=[r for r in rows if r['complete'] and not r['error']]
    ttft=[r['first_token_seconds'] for r in successful if r['first_token_seconds'] is not None]
    total=[r['total_seconds'] for r in successful]
    markers=sum(len(r['citation_markers']) for r in positives)
    summary={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'api_base':args.base_url,'cases':len(rows),'answerable':len(positives),'unanswerable':len(negatives),
             'successful_requests':len(successful),'answer_match_count':sum(r['answer_match'] for r in rows),
             'answerable_match_count':sum(r['answer_match'] for r in positives),'abstention_match_count':sum(r['answer_match'] for r in negatives),
             'citation_hit_count':sum(bool(r['citation_hit']) for r in positives),
             'citation_support_precision':sum(len(r['supported_markers']) for r in positives)/markers if markers else None,
             'first_token_p50_seconds':statistics.median(ttft) if ttft else None,'first_token_p95_seconds':percentile(ttft,.95),
             'total_p50_seconds':statistics.median(total) if total else None,'total_p95_seconds':percentile(total,.95)}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://localhost:8000')
    parser.add_argument('--corpus',type=Path,default=Path('evaluation/corpus.json'))
    parser.add_argument('--output',type=Path,default=Path('evaluation/results/local'))
    parser.add_argument('--interval',type=float,default=7,help='Seconds between questions; respects current per-user limiter')
    args=parser.parse_args()
    if args.interval<7: parser.error('--interval must be at least 7 seconds')
    run(args)
