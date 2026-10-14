#!/usr/bin/env python3
"""TDOC NEXUS SCRIBE v4.0.0. Chronological Drive archive and GitHub Pages integration."""
import argparse, collections, hashlib, http.server, json, math, mimetypes, re
import sys, unicodedata, urllib.parse
from pathlib import Path
import integrations as I

ROOT = Path(__file__).resolve().parent
STOP = set('a an and are as at be by can did do does for from has have how i in is it me my of on or our that the their then there these they this to was we were what when where which with would you your'.split())

def tokenize(text):
    text = re.sub(r'[_/:.\-]+', ' ', unicodedata.normalize('NFKC',str(text)).casefold())
    return [x for x in re.findall(r'[^\W_]+',text) if len(x)>1 and x not in STOP]

class Archive:
    def __init__(self, corpus=None):
        candidate=Path(corpus) if corpus else ROOT/'.private'/'knowledge.json'
        if not candidate.exists():candidate=ROOT/'knowledge'/'knowledge.json'
        if not candidate.exists():raise ValueError('No local archive. Use --corpus PATH with a Scribe knowledge.json export.')
        if not corpus and candidate==ROOT/'.private'/'knowledge.json':I.verify_private(ROOT,candidate)
        if candidate.stat().st_size>I.MAX_CORPUS_BYTES:raise ValueError('Corpus exceeds 128 MiB.')
        self.data=I.validate(json.loads(candidate.read_text()))
        self.chunks=self.data['chunks']; self.df=collections.Counter()
        self.tfs=[]; self.lengths=[]
        for chunk in self.chunks:
            terms=tokenize(chunk['text']); tf=collections.Counter(terms)
            self.tfs.append(tf); self.lengths.append(len(terms)); self.df.update(tf.keys())
        self.avg=sum(self.lengths)/max(1,len(self.lengths))

    def search(self,query,source=None,limit=10):
        terms=set(tokenize(query)); phrase=query.strip().casefold()
        if not terms:return []
        results=[]; n=len(self.chunks)
        for i,chunk in enumerate(self.chunks):
            if source and chunk['source_id']!=source: continue
            score=0.; matched=0
            for term in terms:
                f=self.tfs[i][term]
                if not f:continue
                matched+=1; df=self.df[term]
                idf=math.log(1+(n-df+.5)/(df+.5))
                score+=idf*f*2.2/(f+1.2*(.25+.75*self.lengths[i]/max(1,self.avg)))
            if not score:continue
            if matched==len(terms):score*=1.5
            if len(phrase)>2 and phrase in chunk['text'].casefold():score+=2
            results.append(dict(chunk,score=score,matched=matched))
        return sorted(results,key=lambda x:(-x['score'],x['id']))[:max(1,min(limit,50))]

def verify_files():
    checksum_file=ROOT/'SHA256SUMS'
    if not checksum_file.exists(): return {'ok':False,'error':'SHA256SUMS is missing.'}
    checks=[]
    for line in checksum_file.read_text().splitlines():
        expected,name=line.split('  ',1); path=(ROOT/name).resolve()
        safe=ROOT==path.parent or ROOT in path.parents
        exists=safe and path.is_file()
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        checks.append({'file':name,'ok':actual==expected,'expected_sha256':expected,'actual_sha256':actual})
    return {'ok':bool(checks) and all(c['ok'] for c in checks),'files_checked':len(checks),'checks':checks}

def verify_notes(path):
    data=json.loads(Path(path).read_text()); previous=None; findings=[]
    for i,entry in enumerate(data.get('events',[])):
        payload={k:v for k,v in entry.items() if k not in ('hash','hash_mode')}
        digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        valid=entry.get('previous_hash')==previous and entry.get('hash')==digest
        findings.append({'event':i,'ok':valid}); previous=entry.get('hash')
    anchored=data.get('anchor')==previous
    return {'ok':bool(findings) and all(f['ok'] for f in findings) and anchored,'events':findings,'anchor_matches':anchored,'anchor':previous,'scope':'Integrity relative to this supplied backup anchor, not independent authenticity.'}

def serve(archive,port):
    if not 1<=port<=65535:raise ValueError('Port must be between 1 and 65535.')
    html=I.render((ROOT/'src/template.html').read_text(),{},(ROOT/'src/app.js').read_text(),(ROOT/'src/loader.js').read_text()).replace('<html lang="en">','<html lang="en" data-scribe-mode="local">',1).encode()
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,fmt,*args):
            # Avoid persisting raw queries, note bodies or credential material.
            sys.stderr.write('[scribe] '+self.command+' '+urllib.parse.urlsplit(self.path).path+'\n')
        def end_headers(self):
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            super().end_headers()
        def reply(self,status,body,mime='application/json; charset=utf-8'):
            if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=True).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            try: hostname=urllib.parse.urlsplit('http://'+self.headers.get('Host','')).hostname
            except ValueError:hostname=None
            if hostname not in ('127.0.0.1','localhost'):
                return self.reply(403,{'error':'Loopback Host header required.'})
            parsed=urllib.parse.urlsplit(self.path)
            if parsed.path in ('/','/index.html'):
                return self.reply(200,html,'text/html; charset=utf-8')
            if parsed.path=='/api/corpus':return self.reply(200,archive.data)
            if parsed.path=='/api/timeline':
                p=urllib.parse.parse_qs(parsed.query);axis=p.get('axis',['created_at'])[0]
                if axis not in ('created_at','modified_at','collected_at'):return self.reply(400,{'error':'Invalid timeline axis.'})
                return self.reply(200,{'axis':axis,'rows':I.timeline(archive.data,axis),'scope':'Recorded source and Drive dates; unknown dates are separate.'})
            if parsed.path=='/api/integrations':
                return self.reply(200,{'github_repository':'machackabook/The-Scribe','pages':'manual_deployment_required','drive':archive.data.get('drive_import') or archive.data.get('drive_sync'),'oauth_tokens':'local_cli_only'})
            if parsed.path=='/api/status':
                return self.reply(200,{'status':'ready','scope':'local-source-archive','version':archive.data['version'],'counts':archive.data['counts'],'ai_transcription':'not_configured','device_verification':'not_performed'})
            if parsed.path=='/api/search':
                p=urllib.parse.parse_qs(parsed.query); q=p.get('q',[''])[0]
                if len(q)>5000:return self.reply(400,{'error':'Query is too long.'})
                try:limit=int(p.get('limit',['10'])[0])
                except ValueError:return self.reply(400,{'error':'Invalid result limit.'})
                rows=archive.search(q,p.get('source',[None])[0],limit)
                return self.reply(200,{'query':q,'results':rows,'mode':'local_retrieval'})
            if parsed.path=='/api/sources':
                return self.reply(200,[{k:v for k,v in s.items() if k!='blocks'} for s in archive.data['sources']])
            raw=urllib.parse.unquote(parsed.path)
            if '\x00' in raw:return self.reply(400,{'error':'Invalid path.'})
            if any(part.startswith('.') for part in Path(raw).parts) or raw.startswith('/src/') or raw.startswith('/tests/') or raw=='/integrations.py':
                return self.reply(404,{'error':'Not found.'})
            file=(ROOT/raw.lstrip('/')).resolve() if raw!='/' else ROOT/'index.html'
            if ROOT not in file.parents or not file.is_file():return self.reply(404,{'error':'Not found.'})
            if file.suffix not in ('.html','.json','.txt','.csv','.md','.jsonl') and file.name!='SHA256SUMS':
                return self.reply(404,{'error':'Not found.'})
            mime=(mimetypes.guess_type(file.name)[0] or 'text/plain')+'; charset=utf-8'
            return self.reply(200,file.read_bytes(),mime)
        def do_POST(self):self.reply(405,{'error':'This local archive server is read-only. Notes remain in the browser.'})
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'NEXUS SCRIBE {archive.data["version"]} | http://127.0.0.1:{server.server_address[1]}',flush=True)
    print('Foreground local server. Press Ctrl+C to stop; your shell remains available.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',help='Explicit local knowledge.json; defaults to private refreshed corpus then packaged baseline')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('sources',help='List source coverage and provenance')
    sub.add_parser('catalog',help='List the observed Google Drive metadata catalog')
    t=sub.add_parser('timeline',help='Chronological source catalog');t.add_argument('--axis',choices=['created_at','modified_at','collected_at'],default='created_at');t.add_argument('--csv',action='store_true')
    p=sub.add_parser('build-pages',help='Build a Pages shell with no private corpus');p.add_argument('--output',required=True)
    sub.add_parser('build-local',help='Rebuild an offline index.html with the current local archive')
    ing=sub.add_parser('ingest',help='Import a Drive connector snapshot with citations');ing.add_argument('snapshot');ing.add_argument('--inventory')
    ds=sub.add_parser('drive-sync',help='Read a project folder through the live Drive API');ds.add_argument('--token-file',required=True);ds.add_argument('--folder-id',required=True);ds.add_argument('--recursive',action='store_true')
    q=sub.add_parser('search',help='Rank real source passages');q.add_argument('query');q.add_argument('--source');q.add_argument('--limit',type=int,default=8);q.add_argument('--json',action='store_true')
    sub.add_parser('verify',help='Verify packaged final-byte SHA-256 checksums')
    n=sub.add_parser('verify-notes',help='Check an exported browser note hash-chain');n.add_argument('backup')
    s=sub.add_parser('serve',help='Serve the local UI and read-only search API');s.add_argument('--port',type=int,default=8787)
    args=parser.parse_args()
    if args.command=='build-pages':
        print(json.dumps(I.build_pages(ROOT,args.output),indent=2));return 0
    if args.command=='verify':
        result=verify_files(); print(json.dumps(result,indent=2));return 0 if result['ok'] else 1
    if args.command=='verify-notes':
        result=verify_notes(args.backup);print(json.dumps(result,indent=2));return 0 if result['ok'] else 1
    if args.command in ('ingest','drive-sync'):
        import fcntl
        folder=ROOT/'.private';folder.mkdir(mode=0o700,exist_ok=True)
        with (folder/'ingestion.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Another Scribe import is active; try again after it completes.')
            archive=Archive(args.corpus)
            if args.command=='ingest':
                payload=Path(args.snapshot)
                if payload.stat().st_size>I.MAX_CORPUS_BYTES:raise ValueError('Snapshot is too large.')
                docs=json.loads(payload.read_text());inventory=json.loads(Path(args.inventory).read_text()) if args.inventory else None
                if not isinstance(docs,list):raise ValueError('Snapshot must be a list of document records.')
                result=I.ingest_drive(archive.data,docs,inventory)
            else:result=I.sync_drive(archive.data,args.token_file,args.folder_id,args.recursive)
            result['receipt']=I.commit_private(ROOT,archive.data,result)
            print(json.dumps(result,indent=2));return 0 if not result['failed'] else 2
    archive=Archive(args.corpus)
    if args.command=='catalog':print(json.dumps(archive.data.get('catalog',[]),ensure_ascii=False,indent=2))
    elif args.command=='timeline':
        rows=I.timeline(archive.data,args.axis);print(I.timeline_csv(rows) if args.csv else json.dumps(rows,ensure_ascii=False,indent=2))
    elif args.command=='build-local':
        output=ROOT/'.private'/'index.html';output.parent.mkdir(mode=0o700,exist_ok=True)
        output.write_text(I.render((ROOT/'src/template.html').read_text(),archive.data,(ROOT/'src/app.js').read_text(),(ROOT/'src/loader.js').read_text()));output.chmod(0o600)
        print(json.dumps({'output':str(output),'version':I.VERSION}))
    elif args.command=='sources':
        print(json.dumps([{k:v for k,v in s.items() if k!='blocks'} for s in archive.data['sources']],indent=2,ensure_ascii=False))
    elif args.command=='search':
        results=archive.search(args.query,args.source,args.limit)
        if args.json:print(json.dumps(results,ensure_ascii=False,indent=2))
        else:
            if not results:print('No source passage matched.')
            for item in results:
                print(f'\n[{item["source_id"]} | {item["locator"]} | {item["status"]}]\n{item["text"][:1400]}')
    elif args.command=='serve':serve(archive,args.port)
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,json.JSONDecodeError) as error:
        print('[BLOCKED] '+str(error),file=sys.stderr);raise SystemExit(1)
