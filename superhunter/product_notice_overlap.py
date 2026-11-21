"""Locate duplicated passages in verified notices with the PMD copy/paste detector."""
from collections import defaultdict
from pathlib import Path
import re
import subprocess
import tempfile

from .product_reasoning import EvidenceError
from .product_review import copy_release, sha
from .safe_io import canonical

DIGEST = 'd27177c185b837fa57f097e482d1253468aa035379c5eb2671fa0a279109b179'
JAVA = r"""import java.nio.file.*;
import java.util.*;
import net.sourceforge.pmd.cpd.*;
import net.sourceforge.pmd.lang.*;
class NoticeBlocks {
    static class Notices extends LanguageModuleBase implements CpdCapableLanguage {
        Notices() { super(LanguageMetadata.withId("notices").name("License notices").extensions("txt")); }
        public CpdLexer createCpdLexer(LanguagePropertyBundle properties) { return new AnyCpdLexer(); }
    }
    public static void main(String[] args) throws Exception {
        CPDConfiguration cfg = new CPDConfiguration(LanguageRegistry.singleton(new Notices()));
        cfg.setMinimumTileSize(45);
        try (CpdAnalysis run = CpdAnalysis.create(cfg)) {
            run.files().addDirectory(Path.of(args[0]));
            run.performAnalysis(report -> {
                if (!report.getProcessingErrors().isEmpty()) throw new IllegalStateException("notice tokenization failed");
                report.getNumberOfTokensPerFile().forEach((id,n) -> System.out.println("F\t" + id.getFileName() + "\t" + n));
                for (var match : report.getMatches()) {
                    System.out.println("B\t" + match.getTokenCount());
                    for (var mark : match.getMarkSet()) {
                        var l = mark.getLocation();
                        System.out.printf("R\t%s\t%d\t%d\t%d\t%d%n",l.getFileId().getFileName(),
                            l.getStartLine(), l.getStartColumn(), l.getEndLine(), l.getEndColumn());
                    }
                }
            });
        }
    }
}
"""

# The release's language-independent lexer treats quoted strings as single tokens.
TOKENS = re.compile(r'''\w+|[^"'\s]|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*' ''', re.ASCII | re.VERBOSE)


def column(text, number):
    raw = text.encode('utf-16-le')
    if not 1 <= number <= len(raw) // 2 + 1:
        raise EvidenceError('invalid PMD source column')
    return len(raw[:2*(number - 1)].decode('utf-16-le'))


def assess(output, notices, *, record_refutations=False):
    lines = {n: raw.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '\n').split('\n')
             for n, raw in notices.items()}
    counts = {}
    groups = []
    for row in output.splitlines():
        fields = row.split('\t')
        if fields[0] == 'F' and len(fields) == 3:
            _, name, count = fields
            if name not in lines or name in counts or len(TOKENS.findall('\n'.join(lines[name]))) != int(count):
                raise EvidenceError('PMD file token count differs from verified notice')
            counts[name] = int(count)
        elif fields[0] == 'B' and len(fields) == 2 and int(fields[1]) >= 45:
            groups.append((int(fields[1]), []))
        elif fields[0] == 'R' and len(fields) == 6 and groups:
            name = fields[1]
            start, left, end, right = map(int, fields[2:])
            if name not in lines or not 1 <= start <= end <= len(lines[name]):
                raise EvidenceError('invalid PMD notice range')
            region = lines[name][start-1:end]
            raw = '\n'.join(region)
            begin = column(region[0], left)
            finish = len(raw) - len(region[-1]) + column(region[-1], right)
            words = TOKENS.findall(raw[begin:finish])
            if len(words) != groups[-1][0]:
                raise EvidenceError('PMD notice span does not contain the reported number of tokens')
            groups[-1][1].append((sha(canonical(words)), name, start, left, end, right))
        else:
            raise EvidenceError('unexpected PMD notice report record')
    if counts.keys() != lines.keys():
        raise EvidenceError('incomplete PMD notice corpus')
    by_file = defaultdict(list)
    passages, refuted = [], []
    for count, locations in groups:
        if len(set(locations)) != len(locations) or len(locations) < 2:
            raise EvidenceError('PMD passage needs distinct source locations')
        if len({r[0] for r in locations}) != 1:
            if not record_refutations:
                raise EvidenceError('PMD passage locations do not identify identical token sequences')
            refuted.append({'state': 'REFUTED', 'reported_tokens': count, 'reason': 'token_sequence_mismatch',
                            'locations': [{'file': n, 'tokens_sha256': digest, 'start': [a, b], 'end': [c, d]}
                                          for digest, n, a, b, c, d in sorted(locations)]})
            continue
        locs = [{'file': name, 'start_line': a, 'start_column': b, 'end_line': c, 'end_column': d}
                for _, name, a, b, c, d in sorted(locations)]
        group = {'tokens': count, 'tokens_sha256': locations[0][0], 'locations': locs}
        passages.append(group)
        for name in {r[1] for r in locations}:
            by_file[name].append(group)
    for rows in [passages, *by_file.values()]:
        rows.sort(key=lambda r: (-r['tokens'], r['tokens_sha256'], canonical(r['locations'])))
    summary = {'documents': len(counts), 'passages': len(passages), 'locations': sum(len(p['locations']) for p in passages),
               'passages_sha256': sha(canonical(passages)), 'version': '7.29.0', 'distribution_sha256': DIGEST}
    if refuted:
        summary['refuted_candidates'] = sorted(refuted, key=canonical)
    return summary, {n: by_file[n] for n in sorted(counts)}


def build(release, notices):
    if not notices:
        raise EvidenceError('PMD notice comparison requires verified wheel notices')
    with tempfile.TemporaryDirectory(prefix='nqc-notice-overlap-') as temp:
        root = Path(temp)
        zipfile = root/'release.zip'
        copy_release('PMD', release, zipfile, DIGEST, executable=False)
        isolate = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']
        env = {'HOME': temp, 'TMPDIR': temp, 'LC_ALL': 'C.UTF-8', 'PATH': '/usr/bin:/bin'}
        subprocess.run([*isolate, '/usr/bin/unzip', '-q', str(zipfile), 'pmd-bin-7.29.0/lib/*'], cwd=root,
                       env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60, check=True)
        (root/'NoticeBlocks.java').write_text(JAVA)
        docs = root/'docs'
        docs.mkdir()
        for name, raw in notices.items():
            (docs/name).write_bytes(raw)
        # Keep VM diagnostics out of the CPD record stream, including during concurrent replays.
        output = subprocess.check_output([*isolate, '/usr/bin/java', '-XX:ActiveProcessorCount=2', '-Xmx512m',
                                         '-XX:-UsePerfData', '-Xlog:all=warning:stderr',
                                         '-cp', str(root/'pmd-bin-7.29.0/lib/*'),
                                         'NoticeBlocks.java', str(docs)], cwd=root, env=env, text=True,
                                        stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90)
    return assess(output, notices, record_refutations=True)
