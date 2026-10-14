#!/usr/bin/env python3
"""Fail a Pages build if it contains anything except the reviewed public interface."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import integrations as I
root=Path(sys.argv[1]);allowed={'index.html','app.js','loader.js','.nojekyll','deployment.json'}
files={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
if files!=allowed:raise SystemExit('Pages file allowlist failed.')
for p in root.rglob('*'):
 if p.is_symlink():raise SystemExit('Symlinks are not permitted in the Pages artifact.')
 if p.is_file():
  import re
  value=p.read_text()
  for pattern in I.PATTERNS:
   if re.search(pattern,value):raise SystemExit('Credential pattern found in Pages artifact; publication blocked.')
html=(root/'index.html').read_text()
payload=html.split('<script id="knowledgeData" type="application/json">',1)[1].split('</script>',1)[0]
if json.loads(payload)!={}:raise SystemExit('Private corpus embedded in Pages artifact; publication blocked.')
manifest=json.loads((root/'deployment.json').read_text())
if manifest.get('published_corpus') or manifest.get('drive_tokens') or manifest.get('embedded_source_count')!=0:raise SystemExit('Pages privacy manifest failed.')
if "connect-src 'none'" not in html:raise SystemExit('Pages network policy is missing.')
print('PASS: Pages interface contains no corpus, credentials, or private source files.')
