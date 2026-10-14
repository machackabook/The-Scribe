#!/usr/bin/env python3
"""TDOC NEXUS-SCRIBE-4.0.0: real, read-only Drive ingestion and provenance."""
import csv, datetime as dt, hashlib, io, json, os, re, shutil, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

VERSION = '4.0.0'
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_CORPUS_BYTES = 128 * 1024 * 1024
PATTERNS = [
    r'AIza[A-Za-z0-9_-]{12,}',
    r'(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{12,}',
    r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}',
    r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{12,}\b',
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    r'(?i:Bearer)\s+[A-Za-z0-9._~+/-]{16,}={0,2}',
]

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def redact(text):
    count = 0
    for pattern in PATTERNS:
        text, n = re.subn(pattern, '[REDACTED_CREDENTIAL]', text); count += n
    def assignment(m):
        nonlocal count
        value = m.group(2)
        if any(x in value for x in ('REDACTED', 'process.env', 'os.environ', '${', 'getenv')): return m.group(0)
        count += 1; return m.group(1) + '"[REDACTED_CREDENTIAL]"'
    text = re.sub(r'((?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret)["\x27]?\s*[:=]\s*)["\x27]([^"\x27\r\n]{8,})["\x27]', assignment, text, flags=re.I)
    text, n = re.subn(r'(?im)^(\s*(?:export\s+)?\w*(?:API_KEY|TOKEN|SECRET|PASSWORD)\w*\s*=)([^\r\n]+)', r'\1[REDACTED_CREDENTIAL]', text); count += n
    text, n = re.subn(r'([?&](?:token|api_key|access_token|refresh_token)=)[^\s"\x27&<>]+', r'\1[REDACTED_CREDENTIAL]', text, flags=re.I); count += n
    return text.replace('\x00',''), count

def valid_time(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError): return None

def validate(data):
    if not isinstance(data, dict) or data.get('schema') != 'nexus-scribe-knowledge/1': raise ValueError('Unsupported corpus schema.')
    for key in ('sources','chunks','records'):
        if not isinstance(data.get(key), list): raise ValueError('Missing corpus ' + key)
    ids = set()
    for source in data['sources']:
        if not isinstance(source.get('id'),str) or source['id'] in ids: raise ValueError('Duplicate or invalid source ID.')
        ids.add(source['id'])
        if not isinstance(source.get('blocks'),list): raise ValueError('Invalid source sections.')
    for chunk in data['chunks']:
        if chunk.get('source_id') not in ids or not isinstance(chunk.get('text'),str): raise ValueError('Unresolved chunk citation.')
    return data

def blocks_for(text):
    lines = text.splitlines(); blocks = []
    for i in range(0,len(lines),80):
        blocks.append({'locator':f'lines {i+1}-{min(i+80,len(lines))}', 'text':'\n'.join(lines[i:i+80])})
    return blocks

def drive_meta(meta):
    return {'id':str(meta['id']), 'name':meta.get('title') or meta.get('name') or str(meta['id']),
            'created_at':meta.get('created_at') or meta.get('createdTime'),
            'modified_at':meta.get('updated_at') or meta.get('modifiedTime'),
            'mime_type':meta.get('mime_type') or meta.get('mimeType'),
            'url':meta.get('display_url') or meta.get('webViewLink') or meta.get('url'),
            'bytes':int(meta.get('size') or 0), 'account':meta.get('account_label','local_oauth'),
            'account_access':meta.get('account_access',[]), 'date_meaning':'Drive file creation/modification; not necessarily original work date'}

def add_source(data, source):
    data['sources'].append(source)
    sid=source['id']
    for i,block in enumerate(source['blocks']):
        raw=block['text']; pos=0; part=0
        while pos < len(raw):
            end=min(pos+3000,len(raw)); part+=1
            snippet=raw[pos:end].strip()
            if snippet: data['chunks'].append({'id':f'{sid}-B{i+1:03d}-C{part:03d}', 'source_id':sid, 'locator':block['locator'], 'offset':pos, 'text':snippet, 'status':source['status']})
            if end==len(raw): break
            pos=end-160
    if source['blocks']:
        data['records'].append({'id':f'IMPORT-{sid}', 'title':source['name'], 'summary':f"Archived {len(source['blocks'])} source sections. Read the cited text for its content and claims. Importing this document does not verify the systems it describes.", 'status':source['status'], 'tags':source['topics'], 'citations':[{'source_id':sid,'locator':source['blocks'][0]['locator']}], 'notes':'Source retrieval only.'})

def ingest_drive(data, documents, inventory=None):
    catalog={item['id']:item for item in data.get('catalog',[])}
    for m in inventory or []: catalog[m['id']]={**drive_meta(m),'content_status':catalog.get(m['id'],{}).get('content_status','catalog_only')}
    result={'added':0,'unchanged':0,'failed':0,'redactions':0}
    for doc in documents:
        m=drive_meta(doc['metadata']); sid='DRV-'+sha(m['id'].encode())[:20]
        text,redactions=redact(doc.get('text','')); redactions+=doc.get('redactions',0)
        result['redactions']+=redactions
        fingerprint=sha(text.encode()) if text else None
        previous=[s for s in data['sources'] if s.get('provenance',{}).get('drive_file_id')==m['id']]
        same=next((s for s in previous if s.get('returned_text_sha256')==fingerprint and bool(s['blocks'])==bool(text)),None)
        catalog[m['id']]={**m,'content_status':doc.get('status','catalog_only'),'source_id':same['id'] if same else sid, 'collected_at':doc.get('collected_at') or now()}
        if same: result['unchanged']+=1; continue
        if previous: sid+='-R'+sha(((fingerprint or '')+now()).encode())[:10]
        catalog[m['id']]['source_id']=sid
        blocks=blocks_for(text)
        status='source_claim' if re.search('implementation.status|complete.documentation',m['name'],re.I) else 'historical_log' if re.search(r'\.log$|transcript',m['name'],re.I) else 'design_source' if text else 'blocked'
        rendered='\n\n'.join(f'[{b["locator"]}]\n{b["text"]}' for b in blocks)
        source={'id':sid,'name':m['name'],'uploaded_name':m['name'],'format':'drive_text','status':status,'bytes':m['bytes'], 'original_sha256':None,'returned_text_sha256':fingerprint,'text_sha256':sha(rendered.encode()),'text_file':None,'characters':len(rendered),'blocks':blocks,'topics':['Drive',m['account'],'project work'],'metadata':m,'created_at':m['created_at'],'modified_at':m['modified_at'], 'provenance':{'provider':'google_drive','drive_file_id':m['id'],'url':m['url'],'account':m['account'],'transport':doc.get('response_metadata',{}).get('content_transport','Drive API text'),'original_bytes_verified':False}, 'errors':[] if text else [doc.get('error') or ('Empty readable text returned.' if doc.get('status')=='empty' else 'Content has not been read.')],'collected_at':doc.get('collected_at') or now(),'source_timezone':'UTC timestamps supplied by Drive; source work date may differ','revision_of':previous[-1]['id'] if previous else None,'redactions':redactions}
        add_source(data,source);result['added']+=1
        if not text: result['failed']+=1
    data['catalog']=list(catalog.values()); recount(data); return result

def recount(data):
    data['version']=VERSION; data['build_at']=now()
    data['counts'].update({'uploads':len(data['sources']), 'readable':sum(bool(s['blocks']) for s in data['sources']), 'blocked':sum(not s['blocks'] for s in data['sources']), 'chunks':len(data['chunks']), 'knowledge_records':len(data['records']), 'text_characters':sum(s['characters'] for s in data['sources']), 'drive_catalog':len(data.get('catalog',[])), 'drive_text':sum(bool(s['blocks']) and s.get('provenance',{}).get('provider')=='google_drive' and s['id'].startswith('DRV-') for s in data['sources'])})
    data['timeline']=timeline(data)

def timeline(data, axis='created_at'):
    rows=[]; linked={c.get('source_id') for c in data.get('catalog',[])}
    for c in data.get('catalog',[]): rows.append({**c,'row_id':'drive:'+c['id'],'origin':'google_drive'})
    for s in data['sources']:
        if s['id'] in linked: continue
        rows.append({'row_id':'source:'+s['id'],'id':s['id'],'source_id':s['id'],'name':s['name'],'origin':'upload','created_at':s.get('created_at'), 'modified_at':s.get('modified_at'),'collected_at':s.get('collected_at'), 'content_status':'readable' if s['blocks'] else 'blocked', 'date_meaning':'Source timestamp only if established; collection time is separate.'})
    return sorted(rows, key=lambda r:(valid_time(r.get(axis)) is None,valid_time(r.get(axis)) or dt.datetime.max.replace(tzinfo=dt.timezone.utc),r['row_id']))

def timeline_csv(rows):
    target=io.StringIO(); writer=csv.writer(target); fields=['origin','name','created_at','modified_at','collected_at','content_status','source_id','url','date_meaning'];writer.writerow(fields)
    for row in rows:
        vals=[str(row.get(k) or '') for k in fields]
        writer.writerow(["'"+v if v.startswith(('=','+','-','@')) else v for v in vals])
    return target.getvalue()

def verify_ledger(path):
    previous=None
    if not path.exists(): return None
    for line in path.read_text().splitlines():
        if not line: continue
        item=json.loads(line); signature=item.pop('hash')
        if item.get('previous_hash')!=previous or sha(canonical(item))!=signature: raise ValueError('Integration ledger integrity failed; preserve evidence before retrying.')
        previous=signature
    anchor=path.with_suffix('.anchor')
    if not anchor.exists() or anchor.read_text().strip()!=previous: raise ValueError('Integration ledger anchor mismatch.')
    return previous

def commit_private(root, data, result):
    validate(data); folder=root/'.private'; folder.mkdir(mode=0o700,exist_ok=True)
    ledger=folder/'integration-ledger.jsonl'; previous=verify_ledger(ledger)
    encoded=json.dumps(data,ensure_ascii=False).encode()
    if len(encoded)>MAX_CORPUS_BYTES: raise ValueError('Corpus exceeds 128 MiB; split imports into project folders.')
    output=folder/'knowledge.json'
    if output.exists():
        backups=folder/'backups';backups.mkdir(mode=0o700,exist_ok=True)
        shutil.copy2(output,backups/(now().replace(':','-')+'.json'))
    temporary=folder/'knowledge.pending';temporary.write_bytes(encoded);temporary.chmod(0o600);os.replace(temporary,output)
    event={'timestamp':now(),'action':'ingest_drive_work','result':result,'corpus_sha256':sha(encoded),'previous_hash':previous};event['hash']=sha(canonical(event))
    with ledger.open('a') as handle: handle.write(json.dumps(event,ensure_ascii=False)+'\n');handle.flush();os.fsync(handle.fileno())
    ledger.chmod(0o600);ledger.with_suffix('.anchor').write_text(event['hash']+'\n');ledger.with_suffix('.anchor').chmod(0o600)
    return {'path':str(output),'anchor':event['hash'],'scope':'Tamper evidence relative to a separately retained anchor.'}

def verify_private(root,corpus):
    ledger=root/'.private'/'integration-ledger.jsonl';verify_ledger(ledger)
    if not ledger.exists():raise ValueError('Private corpus has no integration ledger; use --corpus for an explicit standalone import.')
    rows=[line for line in ledger.read_text().splitlines() if line]
    if not rows or json.loads(rows[-1]).get('corpus_sha256')!=sha(corpus.read_bytes()):raise ValueError('Private corpus differs from its last integration receipt; preserve it and restore a verified backup.')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None

class DriveClient:
    """No writes, embedded credentials, token refresh, or token logging."""
    def __init__(self, token_file):
        path=Path(token_file).expanduser()
        if path.is_symlink() or not path.is_file(): raise ValueError('Use a regular private access-token file.')
        if os.name=='posix' and path.stat().st_mode & 0o077: raise ValueError('Restrict the token file with chmod 600.')
        raw=path.read_text().strip()
        self.token=json.loads(raw)['access_token'] if raw.startswith('{') else raw
        if not self.token or any(c.isspace() for c in self.token): raise ValueError('Invalid access token.')
        self.opener=urllib.request.build_opener(NoRedirect())
    def get(self,path,params=None,limit=MAX_TEXT_BYTES):
        url='https://www.googleapis.com/drive/v3/'+path
        if params: url+='?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+self.token,'Accept':'application/json, text/plain'})
        for attempt in range(3):
            try:
                with self.opener.open(req,timeout=30) as response:
                    raw=response.read(limit+1)
                    if len(raw)>limit: raise ValueError('Drive response exceeds the configured size limit.')
                    return raw
            except urllib.error.HTTPError as error:
                if error.code in (429,500,502,503,504) and attempt<2: time.sleep(2**attempt);continue
                raise ValueError(f'Drive returned HTTP {error.code}; no credential or response body was logged.') from None
        raise ValueError('Drive retries exhausted.')
    def list_files(self,folder_id,recursive=False):
        if not re.fullmatch(r'[\w-]{8,200}',folder_id): raise ValueError('Invalid Drive folder ID.')
        pending=[folder_id];seen=set();files=[]; pages=0
        while pending:
            parent=pending.pop(0)
            if parent in seen:continue
            seen.add(parent);token=None
            while True:
                params={'q':f"'{parent}' in parents and trashed = false",'pageSize':100,'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,size,createdTime,modifiedTime,webViewLink,parents)','orderBy':'modifiedTime','supportsAllDrives':'true','includeItemsFromAllDrives':'true'}
                if token:params['pageToken']=token
                response=json.loads(self.get('files',params));pages+=1
                if pages>1000 or len(files)>10000:raise ValueError('Folder traversal limit reached; choose a smaller project folder.')
                if response.get('incompleteSearch'):raise ValueError('Drive reported an incomplete search; choose a specific project folder.')
                for item in response.get('files',[]):
                    if item['mimeType']=='application/vnd.google-apps.folder':
                        if recursive:pending.append(item['id'])
                    else:files.append(item)
                next_token=response.get('nextPageToken')
                if not next_token:break
                if next_token==token:raise ValueError('Drive repeated a pagination cursor.')
                token=next_token
        return files
    def text(self,item):
        file_id=urllib.parse.quote(item['id'],safe=''); mime=item['mimeType']
        native={'application/vnd.google-apps.document':'text/plain','application/vnd.google-apps.spreadsheet':'text/csv','application/vnd.google-apps.presentation':'text/plain'}
        if mime in native: raw=self.get('files/'+file_id+'/export',{'mimeType':native[mime]})
        elif mime.startswith('text/') or mime in ('application/json','application/javascript','application/x-sh','application/xml'): raw=self.get('files/'+file_id,{'alt':'media'})
        else:raise ValueError('This MIME type requires a text extraction or connector snapshot import.')
        return raw.decode('utf-8-sig')

def sync_drive(data,token_file,folder_id,recursive=False):
    client=DriveClient(token_file);inventory=client.list_files(folder_id,recursive); documents=[]
    for item in inventory:
        try:
            text=client.text(item);clean,count=redact(text)
            documents.append({'metadata':item,'text':clean,'redactions':count,'status':'readable' if clean.strip() else 'empty','collected_at':now(),'response_metadata':{'content_transport':'Drive v3 export or media GET'}})
        except (ValueError,UnicodeDecodeError):documents.append({'metadata':item,'status':'fetch_failed','error':'Unsupported text format, size limit, or Drive read failure; inspect MIME type and authorization locally.','collected_at':now()})
    result=ingest_drive(data,documents,inventory)
    data['drive_sync']={'timestamp':now(),'folder_id':folder_id,'recursive':recursive,'inventory_complete':True,'files':len(inventory),'result':result,'writes_to_drive':0,'native_sheet_scope':'CSV export includes one sheet; use a connector snapshot for all sheets.'}
    return result

def render(template,data,app_js,loader_js):
    encoded=json.dumps(data,ensure_ascii=True,separators=(',',':')).replace('<','\\u003c')
    return template.replace('__KNOWLEDGE_DATA__',encoded).replace('__APPLICATION_JS__',app_js).replace('__LOADER_JS__',loader_js)

def build_pages(root,output):
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('Choose an empty output directory; existing files are preserved.')
    output.mkdir(parents=True,exist_ok=True)
    template=(root/'src'/'template.html').read_text(); app=(root/'src'/'app.js').read_text(); loader=(root/'src'/'loader.js').read_text()
    shell=render(template,{},app,loader)
    shell=shell.replace('<script>'+app+'</script>','<script src="./app.js" defer></script>').replace('<script>'+loader+'</script>','<script src="./loader.js" defer></script>')
    shell=shell.replace('<head>', '<head>\n<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\'; style-src \'unsafe-inline\'; img-src data: blob:; media-src blob:; connect-src \'none\'; base-uri \'none\'; object-src \'none\'; form-action \'none\'">',1)
    (output/'index.html').write_text(shell);(output/'app.js').write_text(app);(output/'loader.js').write_text(loader);(output/'.nojekyll').write_text('')
    (output/'deployment.json').write_text(json.dumps({'version':VERSION,'mode':'browser_local_import','embedded_source_count':0,'drive_tokens':False,'published_corpus':False},indent=2))
    return {'output':str(output),'embedded_private_documents':0,'files':5}
