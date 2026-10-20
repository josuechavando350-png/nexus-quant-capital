# Isolated historical replay migration review — 2026-10-20

## Exact scope and authorization
The owner explicitly requests execution of the existing NQC historical zero-principal proof, not live trading. This reviewed migration creates one NEW bounded research producer ONLY in public repository josuechavando350-png/nexus-quant-capital, branch research/isolated-historical-replay-20261020, based on immutable main 16e352225ba8a6a931834c4edf3d86d9a2924b7d. It does not change main, any legacy disabled workflow, recovered-source, other branches/repositories, customer apps, Cano, Vercel, permissions or secrets. Precedent: NQC028's isolated public read-only producer and migration review, commit c085be6307d6b5dfde67edf85429ae0d114933a2. This is a separate review, not implicit certification inherited from NQC028.

## Source identity
The prior attached NQC_replay_historico_pendiente.zip SHA256 is 2c0e4f360db718da721a550b3e705fda21ecfdf6fad941dd06a1368d6ed10191. Its Solidity executor, Solidity tests and foundry.toml are preserved byte-identically in the bundle. New Python files only supply finite transport, tool verification and execution. The bundle contains exactly six UTF-8 files listed in MANIFEST.json, SHA256 712bc3461b04bb6411947ae0bed68704de2ff825e29ba05ee31d47f7c8918514, 10052 bytes, Git blob f1a1bab5ee254cba6f760fa36cf716fed62abdd8. One transcription-damaged unreferenced blob was rejected by Git SHA before tree publication; it is not in this producer.

Publish source first; only then pin that source commit in the new workflow .github/workflows/nqc-isolated-historical-replay.yml. Only an exact branch/path push may trigger it, run_attempt=1, read-only contents permission, standard ubuntu-24.04 public runner, maximum 18 minutes, no schedule, no dispatch, no cache or artifact uploads, no third-party Actions, no persistent service. Public standard runner usage is free per GitHub documentation; no paid/larger runner or subscription is authorized.

## Tools
Download ONLY official Foundry v1.3.1 linux_amd64 release, SHA256 baad3e1b06d6f310d210c93e95258a03d923fe610f8d0742138f2245f94abd7c, and solc 0.8.26+commit.8a97fa7a native Linux, SHA256 d5f23436f443edb85d8e76906d12f0a86ce0490e7663a9e608efeb7a93f149ef. Verify size/hash before execution. No package manager installer, extra dependencies or credentials. Compile offline before historical reads. Software downloads are distinct from RPC requests.

## Historical read limits
Use ONLY https://ethereum-rpc.publicnode.com, already documented/reached by NQC028, through a localhost whitelist gate. No Blockscout quota reset, Desktop Commander call, Triport, alternate provider, private key or paid endpoint. Maximum 1200 total upstream reads and 600 seconds, sequential, 350ms separation, 20-second HTTP timeout, 8 MiB response cap, cached duplicate reads. No retries after failure. Halt on any access/rate/RPC error, null historical result, size/time/request limit. No latest/pending fallback, eth_call, signing, sends, state overrides or chain writes. The finite read gate accepts chain ID; block metadata within target minus 256 through target; the target/prefix transaction identities; account code/balance/nonce/storage only at parent 21762896. Foundry runs the prefix locally. Network is ordinary GitHub runner access, not an attempt to alter the chat container network policy.

## Economic proof
Target 0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb, Ethereum block 21762897 index 1. Validate block/parent hashes, timestamp, base fee, previous transaction and original receipt, without substituting data after a conflict. createSelectFork by transaction hash must replay the prefix and stop BEFORE target. Run original token/payment parity first. Only on PASS run zero-principal real-protocol variant, economic-floor rollback and callback authentication. No mint/deal/etch/store/mock/oracle replacement. The variant test uses sponsorPayment=0 solely to isolate the token path: this is NOT free sponsorship. gasleft scopes are NOT billed full transaction receipts. Even a passing EVM token path does not approve complete financed net profitability, inclusion, no-recourse terms or realized NQC profit.

## Validation and admission
12 new offline transport-policy tests pass locally; compiler and EVM execution not yet run. Before network, run original isolation verifier and affected isolation tests on a clean BASE worktree; verify source hashes, exact producer parents and additive-only four-path scope. The unchanged global verifier rejects the NEW producer's active workflow by design; record this separately and require only the known forbidden-active-tree error, never relabel producer as globally certified. Rust/full historical certification suites are not run; immutable source unaffected. commercial_admission=false, canary_enabled=false, sponsor_accepted=false and realized_NQC_profit=null regardless of compiler/CI success.

## Result handling
Log tool versions, hashes, compiler errors, anchored receipt metadata, test output, request counts and NQC_RESULT. Raw HTTP read records remain on the ephemeral runner with integrity hashes; do not claim they were downloaded if only logs are retrieved. No background profit monitoring or unattended recurrence is created. A technical failure is neither success nor a refutation of all NQC.

## Primary references reviewed
https://docs.github.com/en/billing/concepts/product-billing/github-actions
https://www.getfoundry.sh/reference/cheatcodes/create-select-fork
https://ethereum.publicnode.com
https://github.com/foundry-rs/foundry/releases/tag/v1.3.1
https://binaries.soliditylang.org/linux-amd64/list.json
