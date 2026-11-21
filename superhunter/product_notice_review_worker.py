"""Isolated worker for the pinned LlamaIndex and LangGraph notice review libraries."""
import json
from pathlib import Path
import re
import sys
from typing import TypedDict


class ReviewState(TypedDict, total=False):
    wheel: dict
    declared: str
    detected: list
    verdict: str


def review_graph():
    from langgraph.graph import END, START, StateGraph
    graph = StateGraph(ReviewState)
    graph.add_node('read_declaration', lambda s: {'declared': ' '.join((s['wheel']['declaration'] or '').split())})
    graph.add_node('read_notices', lambda s: {'detected': [' '.join((x or '').split()) for x in s['wheel']['observed']]})
    def route(s):
        if s['wheel']['digest'] is None:
            return 'wheel_unverified'
        if not s['declared']:
            return 'declaration_absent'
        if not any(s['detected']):
            return 'notice_expression_absent'
        if any(x and x != s['declared'] for x in s['detected']):
            return 'different_text_review'
        return 'same_text' if all(s['detected']) else 'partial_text_match'
    graph.add_edge(START, 'read_declaration')
    graph.add_edge('read_declaration', 'read_notices')
    labels = ('wheel_unverified', 'declaration_absent', 'notice_expression_absent', 'different_text_review',
              'same_text', 'partial_text_match')
    for label in labels:
        def close(state, *, verdict=label):
            return {'verdict': verdict}
        graph.add_node(label, close)
        graph.add_edge(label, END)
    graph.add_conditional_edges('read_notices', route, {k: k for k in labels})
    return graph.compile()


def run():
    from hashlib import sha256
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceWindowNodeParser
    from importlib.metadata import version
    def split(text):
        return [s.strip() for s in re.split(r'\n[ \t]*\n', text) if s.strip()]
    parser = SentenceWindowNodeParser.from_defaults(sentence_splitter=split, window_size=1)
    payload = json.loads(Path('input.json').read_bytes())
    documents = {}
    for name, text in payload['texts'].items():
        nodes = parser.get_nodes_from_documents([Document(text=text, id_=name)], show_progress=False)
        documents[name] = [[node.ref_doc_id, sha256(node.metadata['original_text'].encode()).hexdigest(),
                            sha256(node.metadata['window'].encode()).hexdigest()] for node in nodes]
    graph = review_graph()
    decisions = {key: graph.invoke({'wheel': row})['verdict'] for key, row in payload['wheels'].items()}
    Path('output.json').write_text(json.dumps({'windows': documents, 'decisions': decisions,
        'versions': {'llama-index-core': version('llama-index-core'), 'langgraph': version('langgraph')}}))


if __name__ == '__main__':
    sys.path.insert(0, str(Path.cwd()/'lib'))
    run()
