'use strict';
const assert=require('node:assert/strict');const Core=require('../src/app.js');const Import=require('../src/loader.js');
const fs=require('node:fs');
if(!globalThis.crypto)globalThis.crypto=require('node:crypto').webcrypto;
async function main(){
 const source={id:'SRC-SCRIBE',name:'Scribe owners manual',blocks:[{locator:'lines 1-1',text:'The Scribe of Nexus owners manual.'}]};
 const data={schema:'nexus-scribe-knowledge/1',version:'4.0.0',sources:[source],chunks:[{id:'ONE',source_id:source.id,locator:'lines 1-1',text:source.blocks[0].text,status:'design_source'}],records:[],counts:{},promotion:{path:[]},timeline:[{row_id:'known',name:'Scribe',created_at:'2025-07-31T12:22:43.675Z'},{row_id:'unknown',name:'Upload',created_at:null}]};
 Import.validateCorpus(data);assert.equal(Import.timelineRows(data)[0].row_id,'known');assert.equal(Import.timelineRows(data).at(-1).row_id,'unknown');
 assert.equal(new Core.SearchIndex(data.chunks).search('Scribe')[0].source_id,source.id);
 const sealed=await Import.seal(data,'a separate retained archive passphrase');assert.deepEqual(await Import.unseal(sealed,'a separate retained archive passphrase'),data);
 await assert.rejects(Import.unseal(sealed,'a different wrong archive passphrase'));
 const bytes=Buffer.from(sealed.ciphertext,'base64');bytes[0]^=1;sealed.ciphertext=bytes.toString('base64');await assert.rejects(Import.unseal(sealed,'a separate retained archive passphrase'));
 assert.throws(()=>Import.validateCorpus({...data,chunks:[{source_id:'missing',text:'unresolved'}]}));
 if(process.env.SCRIBE_CORPUS){const real=JSON.parse(fs.readFileSync(process.env.SCRIBE_CORPUS,'utf8'));Import.validateCorpus(real);const index=new Core.SearchIndex(real.chunks);assert.ok(index.search('Scribe').length);assert.ok(index.search('OTASONAR').length);assert.ok(index.search('Enclave').length);assert.equal(Import.timelineRows(real).length,real.timeline.length);console.log(`PASS: actual imported corpus, ${real.sources.length} sources and ${real.chunks.length} passages.`);}
 console.log('PASS: citation validation, chronology, search and authenticated vault round-trip/rejection.');
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
