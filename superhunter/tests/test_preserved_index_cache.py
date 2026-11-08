"""Context-bound per-call reuse; each alias still has real bytes and identities."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from superhunter import bundle_recovery as recovery, portable_copy as portable, preserved_index as index, quality, safe_io


class PreservedIndexCacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.archives=self.root/'archives';self.archives.mkdir();self.out=self.root/'index'
        self.digest=quality.sha(safe_io.canonical(quality.source_snapshot()))
        source=self.root/'original';safe_io.write_new_bundle(source,{'data.bin':b'owned-cache-control'})
        saved=self.root/'saved';anchor=recovery.inspect(source)['input_anchor']
        result=recovery.preserve(source,saved,source_digest=self.digest,input_anchor=anchor)
        made=portable.export(saved,self.archives/'a.zip',source_digest=self.digest,input_anchor=anchor,
                             recovery_anchor=result['recovery_anchor'],include_private_bytes=True)
        self.records=[{'id':'a','file':'a.zip',**{key:made[key] for key in index.PINS}}]
        self.alias('b');self.save_manifest()

    def alias(self,name):
        shutil.copyfile(self.archives/'a.zip',self.archives/(name+'.zip'))
        self.records.append({**self.records[0],'id':name,'file':name+'.zip'})

    def save_manifest(self):
        self.records.sort(key=lambda r:r['id']);self.manifest=self.root/'inputs.json'
        self.manifest.write_bytes(safe_io.canonical({'schema_version':1,'profile':index.MANIFEST_PROFILE,'archives':self.records}))
        self.anchor=quality.sha(self.manifest.read_bytes())

    def build(self):
        return index.build(self.manifest,self.archives,self.out,source_digest=self.digest,manifest_anchor=self.anchor)

    def test_64_aliases_reuse_one_content_check_but_keep_64_entries(self):
        for number in range(62):self.alias(f'copy-{number:02d}')
        self.save_manifest()
        with patch.object(portable,'verify',wraps=portable.verify) as checked:
            result=self.build();self.assertEqual(checked.call_count,1)
        self.assertEqual(result['counts']['entries'],64);self.assertEqual(result['counts']['unique_archives'],1)
        self.assertEqual(result['counts']['duplicate_archive_entries'],63)
        self.assertFalse(result['independent_experiments_proved'])

    def test_distinct_contexts_never_share_content_check(self):
        path=self.archives/'b.zip';saved=portable._decode(path.read_bytes());report=json.loads(saved['recovery.json'])
        report['source_digest']='1'*64;saved['recovery.json']=safe_io.canonical(report)
        saved['COMPLETE.json']=safe_io.canonical({'schema_version':1,'sha256':{n:quality.sha(v) for n,v in saved.items() if n!='COMPLETE.json'}})
        path.write_bytes(portable._encode(saved));self.records[1].update(preserved_source_digest='1'*64,
            recovery_anchor=quality.sha(saved['COMPLETE.json']),archive_anchor=quality.sha(path.read_bytes()))
        self.save_manifest()
        with patch.object(portable,'verify',wraps=portable.verify) as checked:
            result=self.build();self.assertEqual(checked.call_count,2)
        self.assertEqual(result['counts']['unique_archives'],2)
        self.assertEqual(result['counts']['unique_input_inventories'],1)

    def test_same_archive_with_conflicting_any_producer_or_content_pin_rejects(self):
        original=dict(self.records[1])
        for key in ('preserved_source_digest','input_anchor','recovery_anchor'):
            self.records[1]={**original,key:'0'*64};self.save_manifest()
            with self.subTest(key=key),self.assertRaises(ValueError):self.build()
            self.assertFalse(self.out.exists())

    def test_cached_alias_modified_before_its_read_is_rejected(self):
        real=portable.verify
        def change(path,**kwargs):
            result=real(path,**kwargs);p=self.archives/'b.zip';p.write_bytes(p.read_bytes()+b'changed');return result
        with patch.object(portable,'verify',side_effect=change):
            with self.assertRaisesRegex(ValueError,'INDEX_ARCHIVE_ANCHOR'):self.build()

    def test_earlier_file_changed_during_cached_alias_is_rejected(self):
        real=index._stamp;seen=0
        def change(path):
            nonlocal seen
            result=real(path)
            if path.name=='b.zip':
                seen+=1
                if seen==2:
                    first=self.archives/'a.zip';first.write_bytes(first.read_bytes()+b'changed')
            return result
        with patch.object(index,'_stamp',side_effect=change):
            with self.assertRaisesRegex(ValueError,'INDEX_ARCHIVES_CHANGED'):self.build()

    def test_alias_bytes_still_count_towards_total_budget(self):
        budget=(self.archives/'a.zip').stat().st_size
        with patch.object(index,'MAX_TOTAL_BYTES',budget):
            with self.assertRaisesRegex(ValueError,'INDEX_TOTAL_BYTES'):self.build()
        self.assertFalse(self.out.exists())

    def test_reuse_never_persists_across_calls(self):
        with patch.object(portable,'verify',wraps=portable.verify) as checked:
            made=self.build();self.assertEqual(checked.call_count,1)
            index.verify(self.out,self.archives,source_digest=self.digest,manifest_anchor=self.anchor,index_anchor=made['index_anchor'])
            self.assertEqual(checked.call_count,2)
        p=self.archives/'b.zip';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaises(ValueError):
            index.verify(self.out,self.archives,source_digest=self.digest,manifest_anchor=self.anchor,index_anchor=made['index_anchor'])

    def test_source_snapshot_rechecked_after_reused_aliases(self):
        real=index._collect
        def changed(*args):
            result=real(*args);patcher=patch.object(quality,'source_snapshot',return_value={'changed':True})
            patcher.start();self.addCleanup(patcher.stop);return result
        with patch.object(index,'_collect',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'INDEX_SOURCE_CHANGED'):self.build()


if __name__=='__main__':unittest.main()
