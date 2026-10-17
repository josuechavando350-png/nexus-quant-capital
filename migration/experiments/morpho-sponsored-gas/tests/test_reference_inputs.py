import hashlib
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from generate_parity_fixtures import products


class ReferenceInputTests(unittest.TestCase):
    def test_upstream_source_bytes_match_manifest(self):
        for record in json.loads((ROOT/"reference/manifest.json").read_text()):
            with self.subTest(path=record["path"]):
                data=(ROOT/record["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),record["sha256"])
                self.assertEqual(hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest(),record["git_blob"])

    def test_python_fixtures_are_current_before_solidity_parity(self):
        for filename, data in products().items():
            with self.subTest(filename=filename):
                self.assertEqual((ROOT/"fixtures"/filename).read_text(),"0x"+data.hex())
