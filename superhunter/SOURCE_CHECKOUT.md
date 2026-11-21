# Código fuente en NQC · primeros 100 de 200

Este lote incorpora 100 repositorios como submódulos Git directos en `upstream/`. Incluye los 46 proyectos con evidencia funcional anterior y 54 adicionales. El PR 112 documenta las 42 ejecuciones y cuatro referencias que formaban esa base. Los 54 nuevos se contabilizan por código fuente incorporado.

Cada ruta apunta a la revisión inmutable del catálogo de procedencia. Git conserva el código y el historial de cada proveedor en su propio repositorio. Un clon normal de NQC recupera el manifiesto y las revisiones. Para materializar los 100 árboles de trabajo, ejecutar desde la raíz de la rama de producto.

```sh
git submodule update --init --depth 1 --jobs 8
python3 -B -m superhunter product-sources --require-checkout
```

La comprobación coteja la identidad del catálogo, la URL del manifiesto, el commit de cada enlace, el índice de Git y los archivos rastreados del checkout. La opción `--require-checkout` falla ante una fuente ausente o modificada. Los archivos sin seguimiento, las dependencias anidadas y los objetos Git LFS externos quedan fuera de la comprobación. Para consultar sólo las revisiones registradas, usar `python3 -B -m superhunter product-sources`.

| ID del catálogo | Proyecto | Código en NQC | Revisión fijada |
|---:|---|---|---|
| 23 | [meta/Pysa](../upstream/023-pysa) | Nuevo en este lote | [`50ba6ccf2612`](https://github.com/meta/Pysa/tree/50ba6ccf2612131033662e0a6bc5e8acffc6ff36) |
| 27 | [microsoft/playwright](../upstream/027-playwright) | Nuevo en este lote | [`049226728d2d`](https://github.com/microsoft/playwright/tree/049226728d2da8054db18b04782a9848b755855e) |
| 37 | [ethereum/go-ethereum](../upstream/037-go-ethereum) | Nuevo en este lote | [`2b7829ea6aed`](https://github.com/ethereum/go-ethereum/tree/2b7829ea6aed9a95a3fd793cca46731202c6c310) |
| 38 | [bluealloy/revm](../upstream/038-revm) | Nuevo en este lote | [`61eb0f231227`](https://github.com/bluealloy/revm/tree/61eb0f231227db0a89f9cd2cd976cc372b6e94d1) |
| 39 | [OpenZeppelin/openzeppelin-contracts](../upstream/039-openzeppelin-contracts) | Nuevo en este lote | [`5172e1681f05`](https://github.com/OpenZeppelin/openzeppelin-contracts/tree/5172e1681f05f4aa189b7740bf2c0316af67c3b3) |
| 40 | [OpenZeppelin/openzeppelin-upgrades](../upstream/040-openzeppelin-upgrades) | Nuevo en este lote | [`54bb8bb913c2`](https://github.com/OpenZeppelin/openzeppelin-upgrades/tree/54bb8bb913c2d52f417d3bcf1ef94e9061b89da8) |
| 48 | [jaegertracing/jaeger](../upstream/048-jaeger) | Nuevo en este lote | [`f9046f3dadd6`](https://github.com/jaegertracing/jaeger/tree/f9046f3dadd6778e0b2995bc6b41fdf35f9381b1) |
| 75 | [prowler-cloud/prowler](../upstream/075-prowler) | Nuevo en este lote | [`02d631d3a5db`](https://github.com/prowler-cloud/prowler/tree/02d631d3a5db2c8676e9703aec286c7723a32e6f) |
| 76 | [kubescape/kubescape](../upstream/076-kubescape) | Nuevo en este lote | [`ef4faa945647`](https://github.com/kubescape/kubescape/tree/ef4faa945647cdd735f6aa3346567092f51c3a6a) |
| 77 | [aquasecurity/kube-bench](../upstream/077-kube-bench) | Nuevo en este lote | [`e278a5915a98`](https://github.com/aquasecurity/kube-bench/tree/e278a5915a982f2756026de6e2f9ca77077ef9f9) |
| 80 | [cartography-cncf/cartography](../upstream/080-cartography) | Nuevo en este lote | [`ce236e196bbe`](https://github.com/cartography-cncf/cartography/tree/ce236e196bbec30c99502e6ff5ac809a23b2ec42) |
| 82 | [stackrox/kube-linter](../upstream/082-kube-linter) | Nuevo en este lote | [`85cdcb9843fe`](https://github.com/stackrox/kube-linter/tree/85cdcb9843fe07f0bf7d82026de0e79e4b517576) |
| 83 | [cilium/cilium](../upstream/083-cilium) | Nuevo en este lote | [`fb070362cec9`](https://github.com/cilium/cilium/tree/fb070362cec985b65e10d733365b1f34839dbf5b) |
| 85 | [salesforce/policy_sentry](../upstream/085-policy_sentry) | Nuevo en este lote | [`2575f2b873e1`](https://github.com/salesforce/policy_sentry/tree/2575f2b873e1c1f0fb604a448dee392f39ad74ad) |
| 86 | [falcosecurity/falco](../upstream/086-falco) | Nuevo en este lote | [`74ccf76b7b2d`](https://github.com/falcosecurity/falco/tree/74ccf76b7b2d85ff42c97da6bd6a716b0d1d17b9) |
| 88 | [cilium/tetragon](../upstream/088-tetragon) | Nuevo en este lote | [`951e79711c67`](https://github.com/cilium/tetragon/tree/951e79711c673ac932528b535471f895cd8b0094) |
| 89 | [cilium/hubble](../upstream/089-hubble) | Nuevo en este lote | [`35bf8033a880`](https://github.com/cilium/hubble/tree/35bf8033a880ac9b04bd0499067615de4815585b) |
| 93 | [OISF/suricata](../upstream/093-suricata) | Nuevo en este lote | [`5c7787ed61ad`](https://github.com/OISF/suricata/tree/5c7787ed61adb1aa7a26c23e093992350fc97d62) |
| 101 | [meta/infer](../upstream/101-infer) | Nuevo en este lote | [`2ebceff7ce3c`](https://github.com/meta/infer/tree/2ebceff7ce3c93480bbc0e8d09d11aeec53595d8) |
| 102 | [Ericsson/codechecker](../upstream/102-codechecker) | Nuevo en este lote | [`53222cd5d756`](https://github.com/Ericsson/codechecker/tree/53222cd5d7566c553d8d7edbb5134a35a56ef15e) |
| 103 | [cppcheck-opensource/cppcheck](../upstream/103-cppcheck) | Nuevo en este lote | [`e1b5791564c6`](https://github.com/cppcheck-opensource/cppcheck/tree/e1b5791564c662c7dacbc62835f6abe5431aa00b) |
| 104 | [PyCQA/bandit](../upstream/104-bandit) | Nuevo en este lote | [`2d5467c45c31`](https://github.com/PyCQA/bandit/tree/2d5467c45c3189f4d7d07e8022276bc73a478abd) |
| 105 | [securego/gosec](../upstream/105-gosec) | Nuevo en este lote | [`244f1f6f4d1d`](https://github.com/securego/gosec/tree/244f1f6f4d1d0d14f89e79a73dab1219eabb5228) |
| 106 | [phpstan/phpstan](../upstream/106-phpstan) | Nuevo en este lote | [`043348b55e6c`](https://github.com/phpstan/phpstan/tree/043348b55e6c54effbdc0cd2f86173bc00ddd0c2) |
| 107 | [vimeo/psalm](../upstream/107-psalm) | Nuevo en este lote | [`2da2040e23d8`](https://github.com/vimeo/psalm/tree/2da2040e23d8b54e61be22618bd53517b6bd43df) |
| 109 | [spotbugs/spotbugs](../upstream/109-spotbugs) | Nuevo en este lote | [`f4544188eb47`](https://github.com/spotbugs/spotbugs/tree/f4544188eb473d60221572fc0d5645325c8b18eb) |
| 110 | [find-sec-bugs/find-sec-bugs](../upstream/110-find-sec-bugs) | Nuevo en este lote | [`aa1293a6339a`](https://github.com/find-sec-bugs/find-sec-bugs/tree/aa1293a6339a04ddf954670fc550847d1bcd83be) |
| 137 | [anchore/grype](../upstream/137-grype) | Nuevo en este lote | [`8b2987cf575c`](https://github.com/anchore/grype/tree/8b2987cf575c69fb715ae4d3b15bb470e3e8f83b) |
| 138 | [dependency-check/DependencyCheck](../upstream/138-dependencycheck) | Nuevo en este lote | [`ae861fc07f84`](https://github.com/dependency-check/DependencyCheck/tree/ae861fc07f84e3d0be75c2ed2e46b498bc03bcc1) |
| 144 | [ossf/package-analysis](../upstream/144-package-analysis) | Nuevo en este lote | [`a149a6f2e117`](https://github.com/ossf/package-analysis/tree/a149a6f2e1179b8f0c05da6845d8513d360e3b1a) |
| 155 | [stanfordnlp/dspy](../upstream/155-dspy) | Nuevo en este lote | [`226d534da38a`](https://github.com/stanfordnlp/dspy/tree/226d534da38ab8a39e4d6383e01e121dab50da51) |
| 161 | [vllm-project/vllm](../upstream/161-vllm) | Nuevo en este lote | [`1bdc437402d6`](https://github.com/vllm-project/vllm/tree/1bdc437402d6eee29d3ca543c91574f8acc72c8d) |
| 162 | [ggml-org/llama.cpp](../upstream/162-llama.cpp) | Nuevo en este lote | [`e6d624b9a4b9`](https://github.com/ggml-org/llama.cpp/tree/e6d624b9a4b95c6b52f5ca384d70b75581f9821a) |
| 163 | [sgl-project/sglang](../upstream/163-sglang) | Nuevo en este lote | [`4ce41378f96d`](https://github.com/sgl-project/sglang/tree/4ce41378f96da24f12e76eae35dfea5bbf35844a) |
| 164 | [huggingface/transformers](../upstream/164-transformers) | Nuevo en este lote | [`2f1bc5e321b9`](https://github.com/huggingface/transformers/tree/2f1bc5e321b9a736200a590d6e7743ccdeb60772) |
| 165 | [langfuse/langfuse](../upstream/165-langfuse) | Nuevo en este lote | [`306cdfb8b38a`](https://github.com/langfuse/langfuse/tree/306cdfb8b38ac8ca35b9c09cebbf2cd110d06978) |
| 166 | [vibrantlabsai/ragas](../upstream/166-ragas) | Nuevo en este lote | [`8c63f10d500c`](https://github.com/vibrantlabsai/ragas/tree/8c63f10d500c44efbf24fdb9e2920de2104c321c) |
| 167 | [promptfoo/promptfoo](../upstream/167-promptfoo) | Nuevo en este lote | [`b1aca6657b8d`](https://github.com/promptfoo/promptfoo/tree/b1aca6657b8d7353815e78a9bd35273ddcd3fccc) |
| 168 | [UKGovernmentBEIS/inspect_ai](../upstream/168-inspect_ai) | Nuevo en este lote | [`82925564c933`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/82925564c9330e5440d490a7d97d037e11e66c9a) |
| 171 | [NomicFoundation/hardhat](../upstream/171-hardhat) | Nuevo en este lote | [`c6a0b31a8bcb`](https://github.com/NomicFoundation/hardhat/tree/c6a0b31a8bcbb839aa2051f700476e2019e5529d) |
| 175 | [paradigmxyz/reth](../upstream/175-reth) | Nuevo en este lote | [`53b5db1c3bc8`](https://github.com/paradigmxyz/reth/tree/53b5db1c3bc841bae679e58a625485d3d44d5b74) |
| 176 | [besu-eth/besu](../upstream/176-besu) | Nuevo en este lote | [`10dc5130f742`](https://github.com/besu-eth/besu/tree/10dc5130f7424488cc5730fca1e98565a313714b) |
| 177 | [ethereum/hive](../upstream/177-hive) | Nuevo en este lote | [`befb5c9edf4e`](https://github.com/ethereum/hive/tree/befb5c9edf4e1df25351e2a4ebdaca15e3d5d01b) |
| 180 | [LiteSVM/litesvm](../upstream/180-litesvm) | Nuevo en este lote | [`c848c5617d1a`](https://github.com/LiteSVM/litesvm/tree/c848c5617d1ae4d3f832fb0ca03e30c611a7ba52) |
| 181 | [anza-xyz/mollusk](../upstream/181-mollusk) | Nuevo en este lote | [`81d1463aabad`](https://github.com/anza-xyz/mollusk/tree/81d1463aabad700c3bb953827215c5dfc81ca61a) |
| 182 | [otter-sec/anchor](../upstream/182-anchor) | Nuevo en este lote | [`98846e3bb753`](https://github.com/otter-sec/anchor/tree/98846e3bb753a2e5b701d58d2655f76c8f41a01e) |
| 183 | [anza-xyz/agave](../upstream/183-agave) | Nuevo en este lote | [`07289a669228`](https://github.com/anza-xyz/agave/tree/07289a6692285a1f3bdb4a1121b24f0c5a589298) |
| 184 | [lfdt-ibc/ibc-go](../upstream/184-ibc-go) | Nuevo en este lote | [`873b622380fb`](https://github.com/lfdt-ibc/ibc-go/tree/873b622380fbbce76ac407c6e0299fcbec557045) |
| 185 | [CosmWasm/cosmwasm](../upstream/185-cosmwasm) | Nuevo en este lote | [`b7da6a4d373f`](https://github.com/CosmWasm/cosmwasm/tree/b7da6a4d373f5fdb7cd752f855271ed9909ec1ce) |
| 186 | [cosmos/cosmos-sdk](../upstream/186-cosmos-sdk) | Nuevo en este lote | [`0c3dd0e3eb54`](https://github.com/cosmos/cosmos-sdk/tree/0c3dd0e3eb5413ea86fddaa9e8fbe8c16fda815b) |
| 187 | [MystenLabs/sui](../upstream/187-sui) | Nuevo en este lote | [`f0f5a5f03da8`](https://github.com/MystenLabs/sui/tree/f0f5a5f03da8ae1a90c3858dafcfa460f851fcf4) |
| 188 | [starkware-libs/cairo](../upstream/188-cairo) | Nuevo en este lote | [`4a078b123ce2`](https://github.com/starkware-libs/cairo/tree/4a078b123ce242b2a04c0eaae790a976a8da469a) |
| 189 | [ethereum/consensus-specs](../upstream/189-consensus-specs) | Nuevo en este lote | [`2d519bc04f0f`](https://github.com/ethereum/consensus-specs/tree/2d519bc04f0f9c52f0e0876f69b238a9523f1ef8) |
| 200 | [OWASP/mastg](../upstream/200-mastg) | Nuevo en este lote | [`e8183038d7a8`](https://github.com/OWASP/mastg/tree/e8183038d7a88c1ac962732d6e3f6e7f40a0251c) |
| 12 | [foundry-rs/foundry](../upstream/012-foundry) | Base previa | [`20ccce88eeb5`](https://github.com/foundry-rs/foundry/tree/20ccce88eeb5d4d78ed0662699706d6b021a692c) |
| 15 | [ack3-ai/wake](../upstream/015-wake) | Base previa | [`237d0b02e09e`](https://github.com/ack3-ai/wake/tree/237d0b02e09e0d6bfc5a6ce06cf5e52db04c643b) |
| 24 | [tree-sitter/tree-sitter](../upstream/024-tree-sitter) | Base previa | [`32594ac6e053`](https://github.com/tree-sitter/tree-sitter/tree/32594ac6e0532a31bcca7fcd043c34ff5e5e007a) |
| 25 | [ast-grep/ast-grep](../upstream/025-ast-grep) | Base previa | [`8a92260ad4b6`](https://github.com/ast-grep/ast-grep/tree/8a92260ad4b65cf4b716518a76b919e6f0d051b8) |
| 28 | [proptest-rs/proptest](../upstream/028-proptest) | Base previa | [`70cf37d46b7d`](https://github.com/proptest-rs/proptest/tree/70cf37d46b7d83393b6ed94c611f8c52209f585d) |
| 30 | [OWASP/ASVS](../upstream/030-asvs) | Base previa | [`82fb2f41cdb6`](https://github.com/OWASP/ASVS/tree/82fb2f41cdb623e0b11e4d9a6b97c4306c1d119c) |
| 35 | [argotorg/solidity](../upstream/035-solidity) | Base previa | [`bc24c77fb97a`](https://github.com/argotorg/solidity/tree/bc24c77fb97afa3a42955a3762f88dac2ee65170) |
| 36 | [ethereum/execution-specs](../upstream/036-execution-specs) | Base previa | [`391d8a05d5cb`](https://github.com/ethereum/execution-specs/tree/391d8a05d5cb182542ac7e7330c858b6ee03f990) |
| 41 | [cvc5/cvc5](../upstream/041-cvc5) | Base previa | [`0782632364f3`](https://github.com/cvc5/cvc5/tree/0782632364f3748b0ccafe2ff3fedcc62917a92c) |
| 43 | [diffblue/cbmc](../upstream/043-cbmc) | Base previa | [`d29720523b36`](https://github.com/diffblue/cbmc/tree/d29720523b363987a3c5ccf6d4255a813fb8fe47) |
| 44 | [model-checking/kani](../upstream/044-kani) | Base previa | [`b62331c9d7c2`](https://github.com/model-checking/kani/tree/b62331c9d7c2acc78559f2d2fbfa11b95e4a0fcc) |
| 45 | [tlaplus/tlaplus](../upstream/045-tlaplus) | Base previa | [`bc1b506bdcad`](https://github.com/tlaplus/tlaplus/tree/bc1b506bdcad80bb518bf3776a9161c34ff0fc4c) |
| 46 | [klee/klee](../upstream/046-klee) | Base previa | [`a01dff0132ca`](https://github.com/klee/klee/tree/a01dff0132caf705de7678c97af2721a734efdc1) |
| 108 | [pmd/pmd](../upstream/108-pmd) | Base previa | [`d37763dbd32b`](https://github.com/pmd/pmd/tree/d37763dbd32bc1db21bc849037594631089743f3) |
| 111 | [microsoft/sarif-sdk](../upstream/111-sarif-sdk) | Base previa | [`724b6a886914`](https://github.com/microsoft/sarif-sdk/tree/724b6a8869142628e2f060115e506f9609a98f73) |
| 120 | [esbmc/esbmc](../upstream/120-esbmc) | Base previa | [`3194304fbf4e`](https://github.com/esbmc/esbmc/tree/3194304fbf4e75b203e0fc422be31059eb096097) |
| 121 | [seahorn/seahorn](../upstream/121-seahorn) | Base previa | [`892780176731`](https://github.com/seahorn/seahorn/tree/892780176731ec8e97bbb9f6b172fcacd77a8ff4) |
| 122 | [dafny-lang/dafny](../upstream/122-dafny) | Base previa | [`8e67e29912aa`](https://github.com/dafny-lang/dafny/tree/8e67e29912aa81b06a8b8e288c7e3046072ea482) |
| 123 | [verus-lang/verus](../upstream/123-verus) | Base previa | [`cc615f27c3d3`](https://github.com/verus-lang/verus/tree/cc615f27c3d3dec80a83324ed333e48f32d8686c) |
| 124 | [GaloisInc/saw-script](../upstream/124-saw-script) | Base previa | [`00e03b6050a9`](https://github.com/GaloisInc/saw-script/tree/00e03b6050a9c7f3867bdf27ddc60c81c298fe96) |
| 125 | [rocq-prover/rocq](../upstream/125-rocq) | Base previa | [`21891774bf01`](https://github.com/rocq-prover/rocq/tree/21891774bf0131945f6cf454e56121d6a4fda02e) |
| 126 | [FStarLang/FStar](../upstream/126-fstar) | Base previa | [`fc1776afe592`](https://github.com/FStarLang/FStar/tree/fc1776afe592ed8eef352c6610614a70d77b3b66) |
| 127 | [verifast/verifast](../upstream/127-verifast) | Base previa | [`0a83dba42db7`](https://github.com/verifast/verifast/tree/0a83dba42db7ce0b445034ece5298afe980e57dc) |
| 128 | [AliveToolkit/alive2](../upstream/128-alive2) | Base previa | [`3bdd4f5e1cef`](https://github.com/AliveToolkit/alive2/tree/3bdd4f5e1cefa47057e93110e707acd11cfe08e4) |
| 131 | [lief-project/LIEF](../upstream/131-lief) | Base previa | [`2a6fdbc5a3af`](https://github.com/lief-project/LIEF/tree/2a6fdbc5a3af9b7ac797514ca38b1175c78f3fcf) |
| 134 | [qemu/qemu](../upstream/134-qemu) | Base previa | [`8f66cb79044c`](https://github.com/qemu/qemu/tree/8f66cb79044c370e3813c56ceb7a75a5ca2d0a0e) |
| 135 | [google/osv-scanner](../upstream/135-osv-scanner) | Base previa | [`84976ca9f198`](https://github.com/google/osv-scanner/tree/84976ca9f19810864f7de74cefb153919f4e663c) |
| 136 | [anchore/syft](../upstream/136-syft) | Base previa | [`139612f0cc25`](https://github.com/anchore/syft/tree/139612f0cc25952bad472ab8ce6a86e4b442da95) |
| 139 | [DependencyTrack/dependency-track](../upstream/139-dependency-track) | Base previa | [`f63e6bb18a4e`](https://github.com/DependencyTrack/dependency-track/tree/f63e6bb18a4e1b6e8cca8539b5caf92ff3d93f5d) |
| 140 | [cdxgen/cdxgen](../upstream/140-cdxgen) | Base previa | [`af131a308eef`](https://github.com/cdxgen/cdxgen/tree/af131a308eef3cfba3cbdee84127a61d1ff6a1a9) |
| 141 | [ossf/scorecard](../upstream/141-scorecard) | Base previa | [`b62c617675f5`](https://github.com/ossf/scorecard/tree/b62c617675f5dd81ba2bf89a065040559f92f8d7) |
| 142 | [guacsec/guac](../upstream/142-guac) | Base previa | [`af8abdb5e1a4`](https://github.com/guacsec/guac/tree/af8abdb5e1a4823f7c2afa1b5fddcbba7fc2e98f) |
| 143 | [in-toto/in-toto](../upstream/143-in-toto) | Base previa | [`e352b43ad7cb`](https://github.com/in-toto/in-toto/tree/e352b43ad7cb8915d84c36d791aa61346152a0a3) |
| 146 | [rustsec/rustsec](../upstream/146-rustsec) | Base previa | [`a57d1d8c7ad3`](https://github.com/rustsec/rustsec/tree/a57d1d8c7ad3d314a1b6d17243fe3b5c74697739) |
| 147 | [EmbarkStudios/cargo-deny](../upstream/147-cargo-deny) | Base previa | [`6d512893fcfe`](https://github.com/EmbarkStudios/cargo-deny/tree/6d512893fcfea934e8e69c5df44132a4970c42d0) |
| 150 | [aboutcode-org/scancode-toolkit](../upstream/150-scancode-toolkit) | Base previa | [`e423b48a1fdb`](https://github.com/aboutcode-org/scancode-toolkit/tree/e423b48a1fdbff26219fbeafe7e9bdef293b91fc) |
| 154 | [langchain-ai/langgraph](../upstream/154-langgraph) | Base previa | [`c6335a4255dc`](https://github.com/langchain-ai/langgraph/tree/c6335a4255dc1d8abc25a7677f9c072c7ab27b9c) |
| 157 | [deepset-ai/haystack](../upstream/157-haystack) | Base previa | [`85b8d4e0b833`](https://github.com/deepset-ai/haystack/tree/85b8d4e0b8332a60002c3e06972386476fba6b7a) |
| 158 | [run-llama/llama_index](../upstream/158-llama_index) | Base previa | [`99d7433f6f71`](https://github.com/run-llama/llama_index/tree/99d7433f6f71888951379ccca9294e272442c832) |
| 159 | [qdrant/qdrant](../upstream/159-qdrant) | Base previa | [`23065a0bf685`](https://github.com/qdrant/qdrant/tree/23065a0bf6857c3e5da45f6c8939cc746cc0580e) |
| 160 | [pgvector/pgvector](../upstream/160-pgvector) | Base previa | [`1d56580cda45`](https://github.com/pgvector/pgvector/tree/1d56580cda45d20b6b197fbe325fb0f6301e33cd) |
| 172 | [ethers-io/ethers.js](../upstream/172-ethers.js) | Base previa | [`3ea4c226dd0b`](https://github.com/ethers-io/ethers.js/tree/3ea4c226dd0b3a074abf90748de9d11192027f4f) |
| 173 | [wevm/viem](../upstream/173-viem) | Base previa | [`2450e26872b4`](https://github.com/wevm/viem/tree/2450e26872b47aac7dc9f098298c04d2e8d4f374) |
| 174 | [ethereumjs/ethereumjs-monorepo](../upstream/174-ethereumjs-monorepo) | Base previa | [`11695f6cec3d`](https://github.com/ethereumjs/ethereumjs-monorepo/tree/11695f6cec3d99e143169e51ee91a0b6d146908f) |
| 190 | [ethereum/EIPs](../upstream/190-eips) | Base previa | [`b4b2ac745e77`](https://github.com/ethereum/EIPs/tree/b4b2ac745e77291d7b47d45665d4e016ab58d31e) |
| 199 | [OWASP/CheatSheetSeries](../upstream/199-cheatsheetseries) | Base previa | [`c2a1e3e32cec`](https://github.com/OWASP/CheatSheetSeries/tree/c2a1e3e32cec12f27be0a3b1e771ce51288a363e) |

[Cobertura funcional previa por proyecto](CATALOG_COVERAGE.md) · [Catálogo de 200 entradas](repositories_200.json).
