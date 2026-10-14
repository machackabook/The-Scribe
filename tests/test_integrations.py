import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import integrations as I

def archive():
 return {'schema':'nexus-scribe-knowledge/1','version':'4.0.0','sources':[],'chunks':[],'records':[],'counts':{},'promotion':{'path':['ORCHBENCH','LIVE_EXECUTION','ADAM_PROOF_GATES','PRODUCTION_VERIFIED','ARCHBENCHSHOP']}}

class IntegrationChecks(unittest.TestCase):
 def test_chronology_keeps_unknown_separate(self):
  data=archive();data['catalog']=[{'id':'old','name':'older','created_at':'2025-07-31T12:22:43.675Z'},{'id':'unknown','name':'unknown','created_at':None},{'id':'new','name':'recent','created_at':'2026-10-14T08:12:56.816Z'}]
  self.assertEqual([r['id'] for r in I.timeline(data)],['old','new','unknown'])
  self.assertIsNone(I.valid_time('2026-10-14T13:32:59'))
 def test_repeat_import_and_revision_preservation(self):
  data=archive();meta={'id':'scribe-doc','title':'NEXUS_SCRIBE_V2_OWNERS_MANUAL.md','created_at':'2025-07-31T12:22:43.675Z'}
  doc={'metadata':meta,'text':'The Scribe of Nexus V2 owners manual','status':'readable'}
  self.assertEqual(I.ingest_drive(data,[doc])['added'],1)
  self.assertEqual(I.ingest_drive(data,[doc])['unchanged'],1)
  doc['text']+='\nVersioned archive.';I.ingest_drive(data,[doc])
  self.assertEqual(len(data['sources']),2);self.assertEqual(data['sources'][1]['revision_of'],data['sources'][0]['id'])
  self.assertEqual(data['sources'][0]['blocks'][0]['text'],'The Scribe of Nexus V2 owners manual')
 def test_ledger_detects_rewritten_history(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);data=archive();I.commit_private(root,data,{'added':0});I.commit_private(root,data,{'added':0})
   ledger=root/'.private/integration-ledger.jsonl';self.assertIsNotNone(I.verify_ledger(ledger));self.assertEqual(len(ledger.read_text().splitlines()),2)
   ledger.write_text(ledger.read_text().replace('ingest_drive_work','altered_work',1))
   with self.assertRaises(ValueError):I.verify_ledger(ledger)
 def test_csv_formula_titles_are_escaped(self):
  result=I.timeline_csv([{'name':'=1+1'}]);self.assertIn("'=1+1",result)
 def test_pages_build_has_empty_corpus(self):
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'site';I.build_pages(root,out)
   html=(out/'index.html').read_text();raw=html.split('<script id="knowledgeData" type="application/json">')[1].split('</script>')[0]
   self.assertEqual(json.loads(raw),{});self.assertIn("connect-src 'none'",html)
   with self.assertRaises(ValueError):I.build_pages(root,out)
 def test_inconsistent_citations_are_rejected(self):
  data=archive();data['chunks']=[{'source_id':'missing','text':'unresolved'}]
  with self.assertRaises(ValueError):I.validate(data)
if __name__=='__main__':unittest.main()
