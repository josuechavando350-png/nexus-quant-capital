"""A local JSON consumer that can only obtain input through defensive admission."""

from .codec import decode
from .files import sha256


class ArtifactReader:
    def __init__(self, engine):
        self.engine = engine

    def read_json(self, raw_request, token):
        admission, snapshot = self.engine.admit_bytes(raw_request, token)
        # Never reopen a pathname after approval. Only the captured bytes enter the parser.
        data = decode(snapshot, max_bytes=1024 * 1024, max_nodes=65536)
        return {"admission": admission, "content_sha256": sha256(snapshot),
                "size_bytes": len(snapshot), "data": data}
