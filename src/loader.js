/* TDOC NEXUS SCRIBE 4.0.0. Files are read locally; no Drive credentials enter this page. */
(() => {
'use strict';
const LIMIT=128*1024*1024, AAD=new TextEncoder().encode('NEXUS-SCRIBE-VAULT/1');
function validateCorpus(data){
 if(!data||data.schema!=='nexus-scribe-knowledge/1'||!Array.isArray(data.sources)||!Array.isArray(data.chunks)||!Array.isArray(data.records))throw Error('Choose a Scribe knowledge.json export.');
 if(data.sources.length>20000||data.chunks.length>150000)throw Error('Split this archive into smaller project collections.');
 const ids=new Set();for(const s of data.sources){if(typeof s.id!=='string'||ids.has(s.id)||typeof s.name!=='string'||!Array.isArray(s.blocks))throw Error('Invalid source record.');ids.add(s.id);for(const b of s.blocks)if(typeof b.text!=='string'||typeof b.locator!=='string')throw Error('Invalid source section.');}
 for(const c of data.chunks)if(!ids.has(c.source_id)||typeof c.text!=='string'||typeof c.locator!=='string')throw Error('A passage has no source citation.');
 for(const r of data.records)if(typeof r.title!=='string'||typeof r.summary!=='string'||!Array.isArray(r.tags)||!r.citations?.length||r.citations.some(c=>!ids.has(c.source_id)))throw Error('Invalid knowledge record citation.');
 if(!data.counts||!data.promotion||!Array.isArray(data.promotion.path))throw Error('Missing archive counts or evidence gates.');
 return data;
}
function timelineRows(data,axis='created_at',query='',account=''){
 const rows=(data.timeline||[]).filter(r=>(!account||r.account===account)&&(!query||String(r.name||'').toLocaleLowerCase().includes(query.toLocaleLowerCase())));
 const t=r=>{const v=r[axis];if(!v||!/(Z|[+-]\d{2}:\d{2})$/.test(v))return Infinity;const n=Date.parse(v);return Number.isFinite(n)?n:Infinity;};
 return rows.slice().sort((a,b)=>{const aa=t(a),bb=t(b);return(aa===bb?0:aa<bb?-1:1)||String(a.row_id||a.id).localeCompare(String(b.row_id||b.id));});
}
function bytes64(bytes){let out='';for(let i=0;i<bytes.length;i+=32768)out+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(out);}
function from64(s){if(typeof s!=='string'||s.length>LIMIT*1.5)throw Error('Invalid vault encoding.');return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
async function keyFor(pass,salt,usage){
 if(pass.length<16)throw Error('Use a passphrase with at least 16 characters.');
 const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(pass),'PBKDF2',false,['deriveKey']);
 return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:600000,hash:'SHA-256'},key,{name:'AES-GCM',length:256},false,usage);
}
async function seal(data,pass){
 validateCorpus(data);const plain=new TextEncoder().encode(JSON.stringify(data));if(plain.length>LIMIT)throw Error('Archive exceeds 128 MiB.');
 const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12)),key=await keyFor(pass,salt,['encrypt']);
 const cipher=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:AAD},key,plain));
 return{schema:'nexus-scribe-vault/1',kdf:'PBKDF2-SHA256',iterations:600000,cipher:'AES-256-GCM',salt:bytes64(salt),iv:bytes64(iv),ciphertext:bytes64(cipher)};
}
async function unseal(vault,pass){
 if(vault?.schema!=='nexus-scribe-vault/1'||vault.kdf!=='PBKDF2-SHA256'||vault.iterations!==600000||vault.cipher!=='AES-256-GCM')throw Error('Unsupported encrypted archive.');
 const salt=from64(vault.salt),iv=from64(vault.iv);if(salt.length!==16||iv.length!==12)throw Error('Invalid vault salt or IV.');
 const key=await keyFor(pass,salt,['decrypt']),plain=await crypto.subtle.decrypt({name:'AES-GCM',iv,additionalData:AAD},key,from64(vault.ciphertext));
 return validateCorpus(JSON.parse(new TextDecoder().decode(plain)));
}
const Core={validateCorpus,timelineRows,seal,unseal};
if(typeof module!=='undefined'&&module.exports)module.exports=Core;
if(typeof document==='undefined')return;
window.ScribeImport=Core;
const $=id=>document.getElementById(id), status=$('importStatus');
let data=JSON.parse($('knowledgeData').textContent),loaded=!!data.sources;
function activate(corpus){data=validateCorpus(corpus);loaded=true;$('knowledgeData').textContent=JSON.stringify(data);$('importOverlay').hidden=true;$('archiveLayout').hidden=false;window.dispatchEvent(new Event('scribe:load'));}
if(loaded){$('importOverlay').hidden=true;$('archiveLayout').hidden=false;}else{$('importOverlay').hidden=false;$('archiveLayout').hidden=true;}
if(!loaded&&document.documentElement.dataset.scribeMode==='local'&&['localhost','127.0.0.1'].includes(location.hostname)){
 status.textContent='Loading the local archive…';fetch('./api/corpus',{credentials:'omit'}).then(r=>{if(!r.ok)throw Error('Local archive returned HTTP '+r.status);return r.json();}).then(activate).catch(e=>{status.textContent='Local load failed: '+e.message+' Choose your archive file to continue.';});
}
$('archiveFile').addEventListener('change',async()=>{
 const file=$('archiveFile').files[0];if(!file)return;
 try{if(loaded)throw Error('Export your notes, then reload the page to import another archive.');if(file.size>LIMIT)throw Error('File exceeds 128 MiB.');status.textContent='Reading your local file…';let corpus=JSON.parse(await file.text());if(corpus.schema==='nexus-scribe-vault/1'){status.textContent='Decrypting locally…';corpus=await unseal(corpus,$('vaultPassphrase').value);}activate(corpus);$('vaultPassphrase').value='';status.textContent='Imported in this tab.';}catch(e){status.textContent='Import failed: '+(e.name==='OperationError'?'Wrong passphrase or damaged encrypted file.':e.message);}
});
$('sealArchive').addEventListener('click',async()=>{
 const note=$('vaultStatus');try{if(!loaded)throw Error('Import an archive first.');if(!crypto?.subtle)throw Error('Encryption requires localhost or HTTPS.');const pass=$('exportPassphrase').value;note.textContent='Encrypting the archive locally…';const vault=await seal(data,pass);const url=URL.createObjectURL(new Blob([JSON.stringify(vault)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='NEXUS_SCRIBE_v4.0.0.vault.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);$('exportPassphrase').value='';note.textContent='Encrypted archive downloaded. Keep its passphrase separately; it cannot be recovered.';}catch(e){note.textContent='Export failed: '+e.message;}
});
})();
