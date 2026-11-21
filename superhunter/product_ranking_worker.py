"""Operate the verified Haystack in-memory index over normalized public notice tokens."""
from importlib.metadata import version
import json
from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path('lib').resolve()))
    from haystack import Document
    from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    from haystack.document_stores.in_memory import InMemoryDocumentStore
    docs = json.loads(Path('documents.json').read_bytes())
    store = InMemoryDocumentStore(bm25_algorithm='BM25Plus', bm25_tokenization_regex=r'[a-z0-9]+',
                                  bm25_parameters={'k1': 1.5, 'b': .75, 'delta': 1.0})
    store.write_documents([Document(id=name, content=doc['text'], meta={'sha256': doc['sha256']})
                           for name, doc in docs.items()])
    if {d.id: {'text': d.content, 'sha256': d.meta['sha256']} for d in store.filter_documents()} != docs:
        raise ValueError('indexed Haystack documents differ from corpus')
    retriever = InMemoryBM25Retriever(store, top_k=len(docs))
    print(json.dumps({'version': version('haystack-ai'), 'documents': store.count_documents()}), flush=True)
    for line in sys.stdin.buffer:
        query = ' '.join(json.loads(line)['terms'])
        results = retriever.run(query=query)['documents'] if query else []
        print(json.dumps({'hits': [{'file': r.id, 'sha256': r.meta['sha256'], 'score': r.score}
                                   for r in results]}), flush=True)


if __name__ == '__main__':
    main()
