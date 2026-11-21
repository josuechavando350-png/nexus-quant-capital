# Código fuente en NQC · 153 de 200

En los 153 checkouts completos se observaron 115 gitlinks anidados y un puntero Git LFS. En los 47 proyectos pendientes de checkout, se verificaron por separado los objetos de commit y los árboles recursivos. Allí se identificaron otros 26 gitlinks anidados. Dos proyectos de esos 47 aportan extractos con uso funcional. [Prueba offline de los 47 commits y 34 manifiestos](OFFLINE_SOURCE_AND_GO.md). [Inventario por revisión y verificación de las licencias](SOURCE_AUDIT.md) · [Estado funcional de los 200](INTEGRATION_STATUS_200.md).

La rama de producto contiene 153 repositorios como submódulos Git directos en `upstream/`. Los primeros 100 se incorporaron en el PR 113 y este lote añade 53. Las otras 47 identidades tienen una entrada en el catálogo de procedencia. Cada tabla conserva los ID originales.

| Medida | Repositorios |
|---|---:|
| Código fuente previo | 100 |
| Código fuente añadido en este lote | 53 |
| Total con un commit registrado en el árbol Git de NQC | 153 |
| Sólo en el catálogo | 47 |

El inventario de fuentes registra los commits que Git puede recuperar. Los recibos funcionales se publican por separado. En el PR 112 había 42 proyectos con código ejecutado y cuatro referencias contrastadas. [Cobertura funcional por proyecto](CATALOG_COVERAGE.md).

## Verificar el checkout

En la raíz de la rama de producto, estos comandos descargan los submódulos directos y verifican su revisión y archivos rastreados. La salida JSON contiene los campos `count`, `catalog_only_count`, `sources` y `catalog_only`. Esta última lista identifica las 47 entradas sin submódulo por nombre e ID.

```sh
git submodule update --init --depth 1 --jobs 8
python3 -B -m superhunter product-sources --require-checkout
```

Para consultar las revisiones registradas en el árbol Git basta ejecutar `python3 -B -m superhunter product-sources`. La verificación del checkout también comprueba el índice y los archivos rastreados de cada proveedor. Los submódulos anidados, los archivos sin seguimiento y los objetos externos de Git LFS quedan fuera de esa comprobación.

## Las 53 incorporaciones

| ID | Repositorio | Commit verificado |
|---:|---|---|
| 4 | [schemathesis/schemathesis](../upstream/004-schemathesis) | [`6bf8e2749411`](https://github.com/schemathesis/schemathesis/tree/6bf8e2749411a8d692bdaaad8227a1be0ee3d43f) |
| 13 | [crytic/slither](../upstream/013-slither) | [`97c1d10d8107`](https://github.com/crytic/slither/tree/97c1d10d8107e76a9426dd484c03c1afd846c186) |
| 14 | [crytic/echidna](../upstream/014-echidna) | [`fb0fd78b9c3c`](https://github.com/crytic/echidna/tree/fb0fd78b9c3c46ac4127279da2313e727a66e5ad) |
| 16 | [crytic/medusa](../upstream/016-medusa) | [`b86c3bbafb9e`](https://github.com/crytic/medusa/tree/b86c3bbafb9e80f7dcb09533006ecb15dbbbdc98) |
| 17 | [argotorg/hevm](../upstream/017-hevm) | [`87598e81c044`](https://github.com/argotorg/hevm/tree/87598e81c044e2889e4a42e9fd706bd5396448f2) |
| 18 | [crytic/properties](../upstream/018-properties) | [`5ea14b813ff2`](https://github.com/crytic/properties/tree/5ea14b813ff296e24b4257ab52a0402360f916f6) |
| 20 | [shazow/whatsabi](../upstream/020-whatsabi) | [`eefa62383640`](https://github.com/shazow/whatsabi/tree/eefa62383640b9056aade49d1d5ed2206ffcdb3b) |
| 22 | [Fraunhofer-AISEC/cpg](../upstream/022-cpg) | [`8a4bd21ec859`](https://github.com/Fraunhofer-AISEC/cpg/tree/8a4bd21ec8591b1bc92ca6174a01ab5159514e09) |
| 26 | [mitmproxy/mitmproxy](../upstream/026-mitmproxy) | [`c491986978a6`](https://github.com/mitmproxy/mitmproxy/tree/c491986978a6280c29977482cb18698d6523a662) |
| 31 | [runtimeverification/evm-semantics](../upstream/031-evm-semantics) | [`fbb2edbb8e84`](https://github.com/runtimeverification/evm-semantics/tree/fbb2edbb8e84bb05b6ba7a255ce1f44f76051ad1) |
| 32 | [trailofbits/mewt](../upstream/032-mewt) | [`e96e71969ae9`](https://github.com/trailofbits/mewt/tree/e96e71969ae9b9d3ef7562ae5a3a60de6050c0d0) |
| 33 | [Jon-Becker/heimdall-rs](../upstream/033-heimdall-rs) | [`89e107f033f6`](https://github.com/Jon-Becker/heimdall-rs/tree/89e107f033f6e8fc037ba58757ac855e2a7049dd) |
| 34 | [cdump/evmole](../upstream/034-evmole) | [`763f2984f6be`](https://github.com/cdump/evmole/tree/763f2984f6be5ea33636336e804022c75318a260) |
| 42 | [AFLplusplus/AFLplusplus](../upstream/042-aflplusplus) | [`d798677805de`](https://github.com/AFLplusplus/AFLplusplus/tree/d798677805de81b50aa8f45beb0342ae1617b9d8) |
| 47 | [rr-debugger/rr](../upstream/047-rr) | [`f5017a5cea71`](https://github.com/rr-debugger/rr/tree/f5017a5cea712d4958ca72edefd92a0401649bee) |
| 49 | [OWASP/wstg](../upstream/049-wstg) | [`97d915fa54f0`](https://github.com/OWASP/wstg/tree/97d915fa54f0c21b99094acdc5af677be3dc780f) |
| 50 | [strace/strace](../upstream/050-strace) | [`ec439c5485b2`](https://github.com/strace/strace/tree/ec439c5485b234228c1d07a9daf111dafadde75c) |
| 57 | [projectdiscovery/dnsx](../upstream/057-dnsx) | [`f98967b41787`](https://github.com/projectdiscovery/dnsx/tree/f98967b4178790e5a3654c5d9c822dc3544db793) |
| 59 | [projectdiscovery/tlsx](../upstream/059-tlsx) | [`53e3d20a14f9`](https://github.com/projectdiscovery/tlsx/tree/53e3d20a14f917e423c970b4db2944a202e6549a) |
| 61 | [blechschmidt/massdns](../upstream/061-massdns) | [`30c380908b4f`](https://github.com/blechschmidt/massdns/tree/30c380908b4f9afd0931d3d83f85884844831846) |
| 65 | [rapid7/recog](../upstream/065-recog) | [`f1191e24332c`](https://github.com/rapid7/recog/tree/f1191e24332c51d6a3d98457f64fba8dec340784) |
| 66 | [nabla-c0d3/sslyze](../upstream/066-sslyze) | [`e064c2c8e7d2`](https://github.com/nabla-c0d3/sslyze/tree/e064c2c8e7d251e5bc5db1a7beb21add5e12a0bc) |
| 69 | [fullstorydev/grpcurl](../upstream/069-grpcurl) | [`f5c25e012bd4`](https://github.com/fullstorydev/grpcurl/tree/f5c25e012bd451b55444679d5457ed3dfbae53de) |
| 72 | [testssl/testssl.sh](../upstream/072-testssl.sh) | [`0f87aca237ae`](https://github.com/testssl/testssl.sh/tree/0f87aca237ae52a35e69a14157c37377a1779908) |
| 84 | [iann0036/iamlive](../upstream/084-iamlive) | [`3ec1a40e560c`](https://github.com/iann0036/iamlive/tree/3ec1a40e560c2f00ec82c50223add810e2567efb) |
| 87 | [aquasecurity/tracee](../upstream/087-tracee) | [`2f9dc40c20b1`](https://github.com/aquasecurity/tracee/tree/2f9dc40c20b17c2ba27f6d92b25e62790bd48a62) |
| 90 | [inspektor-gadget/inspektor-gadget](../upstream/090-inspektor-gadget) | [`24db8bae213b`](https://github.com/inspektor-gadget/inspektor-gadget/tree/24db8bae213b56a0f8f9ed915e607cc8aed1dc31) |
| 91 | [wireshark/wireshark](../upstream/091-wireshark) | [`227644216631`](https://github.com/wireshark/wireshark/tree/2276442166317e2d80346cf0eb2f2744dd17c6c2) |
| 92 | [secdev/scapy](../upstream/092-scapy) | [`3813c08c414a`](https://github.com/secdev/scapy/tree/3813c08c414a30c686136e50c6e80dd9b3b29663) |
| 95 | [the-tcpdump-group/tcpdump](../upstream/095-tcpdump) | [`3541bd5d3863`](https://github.com/the-tcpdump-group/tcpdump/tree/3541bd5d38635e208d7dd47cc6ea2af00dd7ef0c) |
| 97 | [frida/frida](../upstream/097-frida) | [`a93582c832d7`](https://github.com/frida/frida/tree/a93582c832d74de1eaa0ec59994365f6981368db) |
| 98 | [skylot/jadx](../upstream/098-jadx) | [`3cbbc2348141`](https://github.com/skylot/jadx/tree/3cbbc2348141b7b51dbec2b227f334d6785547e6) |
| 99 | [iBotPeaches/Apktool](../upstream/099-apktool) | [`fbaeb4779d7a`](https://github.com/iBotPeaches/Apktool/tree/fbaeb4779d7aaed2c3097cd496de2bc9150ab869) |
| 112 | [google/honggfuzz](../upstream/112-honggfuzz) | [`940b958dfeb6`](https://github.com/google/honggfuzz/tree/940b958dfeb6f9131fd846cae31fcc0fe996ae98) |
| 113 | [CodeIntelligenceTesting/jazzer](../upstream/113-jazzer) | [`bdebf95c4de0`](https://github.com/CodeIntelligenceTesting/jazzer/tree/bdebf95c4de0154f7e6f1666a64d2b951b4a6861) |
| 114 | [google/atheris](../upstream/114-atheris) | [`e36da74cf42b`](https://github.com/google/atheris/tree/e36da74cf42b5834c4e31d7cabb58d796695d29f) |
| 115 | [rust-fuzz/cargo-fuzz](../upstream/115-cargo-fuzz) | [`bf2fc668dafd`](https://github.com/rust-fuzz/cargo-fuzz/tree/bf2fc668dafda5295aa6fd01825ee67b885f0f2b) |
| 116 | [google/fuzztest](../upstream/116-fuzztest) | [`29e1c6a0fc14`](https://github.com/google/fuzztest/tree/29e1c6a0fc149dc108dfff122bd6aac5efbe85b5) |
| 117 | [google/oss-fuzz](../upstream/117-oss-fuzz) | [`48099ac8ad84`](https://github.com/google/oss-fuzz/tree/48099ac8ad840c31d745f6e2a7627195481cb1df) |
| 118 | [trailofbits/polytracker](../upstream/118-polytracker) | [`ae7b5f12e608`](https://github.com/trailofbits/polytracker/tree/ae7b5f12e608f0c9a896cf1af797e4588c7624f9) |
| 119 | [google/clusterfuzzlite](../upstream/119-clusterfuzzlite) | [`52ecc61cb587`](https://github.com/google/clusterfuzzlite/tree/52ecc61cb587ee99c26825a112a21abf19c7448c) |
| 129 | [radareorg/radare2](../upstream/129-radare2) | [`3f321aa3aeda`](https://github.com/radareorg/radare2/tree/3f321aa3aeda3a69fa12b1df9840648c31b4df14) |
| 130 | [rizinorg/cutter](../upstream/130-cutter) | [`d885514bd809`](https://github.com/rizinorg/cutter/tree/d885514bd8092776429a6ed5213b125c17092c77) |
| 132 | [capstone-engine/capstone](../upstream/132-capstone) | [`ccd25ab39eea`](https://github.com/capstone-engine/capstone/tree/ccd25ab39eea534afbb70cfb047310c5a9962553) |
| 133 | [DynamoRIO/dynamorio](../upstream/133-dynamorio) | [`0fd459d944cb`](https://github.com/DynamoRIO/dynamorio/tree/0fd459d944cb13056c7f29eba1d593a637bf3b68) |
| 145 | [ossf/malicious-packages](../upstream/145-malicious-packages) | [`aaefca1f03b5`](https://github.com/ossf/malicious-packages/tree/aaefca1f03b51a4e26db1fad48b172279a2e41a9) |
| 148 | [trufflesecurity/trufflehog](../upstream/148-trufflehog) | [`4ef51f69ca63`](https://github.com/trufflesecurity/trufflehog/tree/4ef51f69ca6347aaa76a5e64a87eac9c0c909f71) |
| 149 | [betterleaks/betterleaks](../upstream/149-betterleaks) | [`4cd708016003`](https://github.com/betterleaks/betterleaks/tree/4cd7080160031ba1c91fd3a58609f4a63af23de1) |
| 151 | [OpenHands/software-agent-sdk](../upstream/151-software-agent-sdk) | [`3a893a1b26de`](https://github.com/OpenHands/software-agent-sdk/tree/3a893a1b26de7ec02cc0dd2427906eea6aea3fc7) |
| 152 | [SWE-agent/mini-swe-agent](../upstream/152-mini-swe-agent) | [`04d809ceab9d`](https://github.com/SWE-agent/mini-swe-agent/tree/04d809ceab9df28f9adaed044884180159172930) |
| 153 | [Aider-AI/aider](../upstream/153-aider) | [`5dc9490bb35f`](https://github.com/Aider-AI/aider/tree/5dc9490bb35f9729ef2c95d00a19ccd30c26339c) |
| 156 | [huggingface/smolagents](../upstream/156-smolagents) | [`99721bdc3b6f`](https://github.com/huggingface/smolagents/tree/99721bdc3b6f502108751a93c5d7f08b1a04ce76) |
| 178 | [crytic/crytic-compile](../upstream/178-crytic-compile) | [`7e8a89ddd771`](https://github.com/crytic/crytic-compile/tree/7e8a89ddd7718d387b0c7b4e43a7391e1a6d79f3) |

## Los 100 anteriores

| ID del catálogo | Proyecto | Código en NQC | Revisión fijada |
|---:|---|---|---|
| 23 | [meta/Pysa](../upstream/023-pysa) | Incorporado en el PR 113 | [`50ba6ccf2612`](https://github.com/meta/Pysa/tree/50ba6ccf2612131033662e0a6bc5e8acffc6ff36) |
| 27 | [microsoft/playwright](../upstream/027-playwright) | Incorporado en el PR 113 | [`049226728d2d`](https://github.com/microsoft/playwright/tree/049226728d2da8054db18b04782a9848b755855e) |
| 37 | [ethereum/go-ethereum](../upstream/037-go-ethereum) | Incorporado en el PR 113 | [`2b7829ea6aed`](https://github.com/ethereum/go-ethereum/tree/2b7829ea6aed9a95a3fd793cca46731202c6c310) |
| 38 | [bluealloy/revm](../upstream/038-revm) | Incorporado en el PR 113 | [`61eb0f231227`](https://github.com/bluealloy/revm/tree/61eb0f231227db0a89f9cd2cd976cc372b6e94d1) |
| 39 | [OpenZeppelin/openzeppelin-contracts](../upstream/039-openzeppelin-contracts) | Incorporado en el PR 113 | [`5172e1681f05`](https://github.com/OpenZeppelin/openzeppelin-contracts/tree/5172e1681f05f4aa189b7740bf2c0316af67c3b3) |
| 40 | [OpenZeppelin/openzeppelin-upgrades](../upstream/040-openzeppelin-upgrades) | Incorporado en el PR 113 | [`54bb8bb913c2`](https://github.com/OpenZeppelin/openzeppelin-upgrades/tree/54bb8bb913c2d52f417d3bcf1ef94e9061b89da8) |
| 48 | [jaegertracing/jaeger](../upstream/048-jaeger) | Incorporado en el PR 113 | [`f9046f3dadd6`](https://github.com/jaegertracing/jaeger/tree/f9046f3dadd6778e0b2995bc6b41fdf35f9381b1) |
| 75 | [prowler-cloud/prowler](../upstream/075-prowler) | Incorporado en el PR 113 | [`02d631d3a5db`](https://github.com/prowler-cloud/prowler/tree/02d631d3a5db2c8676e9703aec286c7723a32e6f) |
| 76 | [kubescape/kubescape](../upstream/076-kubescape) | Incorporado en el PR 113 | [`ef4faa945647`](https://github.com/kubescape/kubescape/tree/ef4faa945647cdd735f6aa3346567092f51c3a6a) |
| 77 | [aquasecurity/kube-bench](../upstream/077-kube-bench) | Incorporado en el PR 113 | [`e278a5915a98`](https://github.com/aquasecurity/kube-bench/tree/e278a5915a982f2756026de6e2f9ca77077ef9f9) |
| 80 | [cartography-cncf/cartography](../upstream/080-cartography) | Incorporado en el PR 113 | [`ce236e196bbe`](https://github.com/cartography-cncf/cartography/tree/ce236e196bbec30c99502e6ff5ac809a23b2ec42) |
| 82 | [stackrox/kube-linter](../upstream/082-kube-linter) | Incorporado en el PR 113 | [`85cdcb9843fe`](https://github.com/stackrox/kube-linter/tree/85cdcb9843fe07f0bf7d82026de0e79e4b517576) |
| 83 | [cilium/cilium](../upstream/083-cilium) | Incorporado en el PR 113 | [`fb070362cec9`](https://github.com/cilium/cilium/tree/fb070362cec985b65e10d733365b1f34839dbf5b) |
| 85 | [salesforce/policy_sentry](../upstream/085-policy_sentry) | Incorporado en el PR 113 | [`2575f2b873e1`](https://github.com/salesforce/policy_sentry/tree/2575f2b873e1c1f0fb604a448dee392f39ad74ad) |
| 86 | [falcosecurity/falco](../upstream/086-falco) | Incorporado en el PR 113 | [`74ccf76b7b2d`](https://github.com/falcosecurity/falco/tree/74ccf76b7b2d85ff42c97da6bd6a716b0d1d17b9) |
| 88 | [cilium/tetragon](../upstream/088-tetragon) | Incorporado en el PR 113 | [`951e79711c67`](https://github.com/cilium/tetragon/tree/951e79711c673ac932528b535471f895cd8b0094) |
| 89 | [cilium/hubble](../upstream/089-hubble) | Incorporado en el PR 113 | [`35bf8033a880`](https://github.com/cilium/hubble/tree/35bf8033a880ac9b04bd0499067615de4815585b) |
| 93 | [OISF/suricata](../upstream/093-suricata) | Incorporado en el PR 113 | [`5c7787ed61ad`](https://github.com/OISF/suricata/tree/5c7787ed61adb1aa7a26c23e093992350fc97d62) |
| 101 | [meta/infer](../upstream/101-infer) | Incorporado en el PR 113 | [`2ebceff7ce3c`](https://github.com/meta/infer/tree/2ebceff7ce3c93480bbc0e8d09d11aeec53595d8) |
| 102 | [Ericsson/codechecker](../upstream/102-codechecker) | Incorporado en el PR 113 | [`53222cd5d756`](https://github.com/Ericsson/codechecker/tree/53222cd5d7566c553d8d7edbb5134a35a56ef15e) |
| 103 | [cppcheck-opensource/cppcheck](../upstream/103-cppcheck) | Incorporado en el PR 113 | [`e1b5791564c6`](https://github.com/cppcheck-opensource/cppcheck/tree/e1b5791564c662c7dacbc62835f6abe5431aa00b) |
| 104 | [PyCQA/bandit](../upstream/104-bandit) | Incorporado en el PR 113 | [`2d5467c45c31`](https://github.com/PyCQA/bandit/tree/2d5467c45c3189f4d7d07e8022276bc73a478abd) |
| 105 | [securego/gosec](../upstream/105-gosec) | Incorporado en el PR 113 | [`244f1f6f4d1d`](https://github.com/securego/gosec/tree/244f1f6f4d1d0d14f89e79a73dab1219eabb5228) |
| 106 | [phpstan/phpstan](../upstream/106-phpstan) | Incorporado en el PR 113 | [`043348b55e6c`](https://github.com/phpstan/phpstan/tree/043348b55e6c54effbdc0cd2f86173bc00ddd0c2) |
| 107 | [vimeo/psalm](../upstream/107-psalm) | Incorporado en el PR 113 | [`2da2040e23d8`](https://github.com/vimeo/psalm/tree/2da2040e23d8b54e61be22618bd53517b6bd43df) |
| 109 | [spotbugs/spotbugs](../upstream/109-spotbugs) | Incorporado en el PR 113 | [`f4544188eb47`](https://github.com/spotbugs/spotbugs/tree/f4544188eb473d60221572fc0d5645325c8b18eb) |
| 110 | [find-sec-bugs/find-sec-bugs](../upstream/110-find-sec-bugs) | Incorporado en el PR 113 | [`aa1293a6339a`](https://github.com/find-sec-bugs/find-sec-bugs/tree/aa1293a6339a04ddf954670fc550847d1bcd83be) |
| 137 | [anchore/grype](../upstream/137-grype) | Incorporado en el PR 113 | [`8b2987cf575c`](https://github.com/anchore/grype/tree/8b2987cf575c69fb715ae4d3b15bb470e3e8f83b) |
| 138 | [dependency-check/DependencyCheck](../upstream/138-dependencycheck) | Incorporado en el PR 113 | [`ae861fc07f84`](https://github.com/dependency-check/DependencyCheck/tree/ae861fc07f84e3d0be75c2ed2e46b498bc03bcc1) |
| 144 | [ossf/package-analysis](../upstream/144-package-analysis) | Incorporado en el PR 113 | [`a149a6f2e117`](https://github.com/ossf/package-analysis/tree/a149a6f2e1179b8f0c05da6845d8513d360e3b1a) |
| 155 | [stanfordnlp/dspy](../upstream/155-dspy) | Incorporado en el PR 113 | [`226d534da38a`](https://github.com/stanfordnlp/dspy/tree/226d534da38ab8a39e4d6383e01e121dab50da51) |
| 161 | [vllm-project/vllm](../upstream/161-vllm) | Incorporado en el PR 113 | [`1bdc437402d6`](https://github.com/vllm-project/vllm/tree/1bdc437402d6eee29d3ca543c91574f8acc72c8d) |
| 162 | [ggml-org/llama.cpp](../upstream/162-llama.cpp) | Incorporado en el PR 113 | [`e6d624b9a4b9`](https://github.com/ggml-org/llama.cpp/tree/e6d624b9a4b95c6b52f5ca384d70b75581f9821a) |
| 163 | [sgl-project/sglang](../upstream/163-sglang) | Incorporado en el PR 113 | [`4ce41378f96d`](https://github.com/sgl-project/sglang/tree/4ce41378f96da24f12e76eae35dfea5bbf35844a) |
| 164 | [huggingface/transformers](../upstream/164-transformers) | Incorporado en el PR 113 | [`2f1bc5e321b9`](https://github.com/huggingface/transformers/tree/2f1bc5e321b9a736200a590d6e7743ccdeb60772) |
| 165 | [langfuse/langfuse](../upstream/165-langfuse) | Incorporado en el PR 113 | [`306cdfb8b38a`](https://github.com/langfuse/langfuse/tree/306cdfb8b38ac8ca35b9c09cebbf2cd110d06978) |
| 166 | [vibrantlabsai/ragas](../upstream/166-ragas) | Incorporado en el PR 113 | [`8c63f10d500c`](https://github.com/vibrantlabsai/ragas/tree/8c63f10d500c44efbf24fdb9e2920de2104c321c) |
| 167 | [promptfoo/promptfoo](../upstream/167-promptfoo) | Incorporado en el PR 113 | [`b1aca6657b8d`](https://github.com/promptfoo/promptfoo/tree/b1aca6657b8d7353815e78a9bd35273ddcd3fccc) |
| 168 | [UKGovernmentBEIS/inspect_ai](../upstream/168-inspect_ai) | Incorporado en el PR 113 | [`82925564c933`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/82925564c9330e5440d490a7d97d037e11e66c9a) |
| 171 | [NomicFoundation/hardhat](../upstream/171-hardhat) | Incorporado en el PR 113 | [`c6a0b31a8bcb`](https://github.com/NomicFoundation/hardhat/tree/c6a0b31a8bcbb839aa2051f700476e2019e5529d) |
| 175 | [paradigmxyz/reth](../upstream/175-reth) | Incorporado en el PR 113 | [`53b5db1c3bc8`](https://github.com/paradigmxyz/reth/tree/53b5db1c3bc841bae679e58a625485d3d44d5b74) |
| 176 | [besu-eth/besu](../upstream/176-besu) | Incorporado en el PR 113 | [`10dc5130f742`](https://github.com/besu-eth/besu/tree/10dc5130f7424488cc5730fca1e98565a313714b) |
| 177 | [ethereum/hive](../upstream/177-hive) | Incorporado en el PR 113 | [`befb5c9edf4e`](https://github.com/ethereum/hive/tree/befb5c9edf4e1df25351e2a4ebdaca15e3d5d01b) |
| 180 | [LiteSVM/litesvm](../upstream/180-litesvm) | Incorporado en el PR 113 | [`c848c5617d1a`](https://github.com/LiteSVM/litesvm/tree/c848c5617d1ae4d3f832fb0ca03e30c611a7ba52) |
| 181 | [anza-xyz/mollusk](../upstream/181-mollusk) | Incorporado en el PR 113 | [`81d1463aabad`](https://github.com/anza-xyz/mollusk/tree/81d1463aabad700c3bb953827215c5dfc81ca61a) |
| 182 | [otter-sec/anchor](../upstream/182-anchor) | Incorporado en el PR 113 | [`98846e3bb753`](https://github.com/otter-sec/anchor/tree/98846e3bb753a2e5b701d58d2655f76c8f41a01e) |
| 183 | [anza-xyz/agave](../upstream/183-agave) | Incorporado en el PR 113 | [`07289a669228`](https://github.com/anza-xyz/agave/tree/07289a6692285a1f3bdb4a1121b24f0c5a589298) |
| 184 | [lfdt-ibc/ibc-go](../upstream/184-ibc-go) | Incorporado en el PR 113 | [`873b622380fb`](https://github.com/lfdt-ibc/ibc-go/tree/873b622380fbbce76ac407c6e0299fcbec557045) |
| 185 | [CosmWasm/cosmwasm](../upstream/185-cosmwasm) | Incorporado en el PR 113 | [`b7da6a4d373f`](https://github.com/CosmWasm/cosmwasm/tree/b7da6a4d373f5fdb7cd752f855271ed9909ec1ce) |
| 186 | [cosmos/cosmos-sdk](../upstream/186-cosmos-sdk) | Incorporado en el PR 113 | [`0c3dd0e3eb54`](https://github.com/cosmos/cosmos-sdk/tree/0c3dd0e3eb5413ea86fddaa9e8fbe8c16fda815b) |
| 187 | [MystenLabs/sui](../upstream/187-sui) | Incorporado en el PR 113 | [`f0f5a5f03da8`](https://github.com/MystenLabs/sui/tree/f0f5a5f03da8ae1a90c3858dafcfa460f851fcf4) |
| 188 | [starkware-libs/cairo](../upstream/188-cairo) | Incorporado en el PR 113 | [`4a078b123ce2`](https://github.com/starkware-libs/cairo/tree/4a078b123ce242b2a04c0eaae790a976a8da469a) |
| 189 | [ethereum/consensus-specs](../upstream/189-consensus-specs) | Incorporado en el PR 113 | [`2d519bc04f0f`](https://github.com/ethereum/consensus-specs/tree/2d519bc04f0f9c52f0e0876f69b238a9523f1ef8) |
| 200 | [OWASP/mastg](../upstream/200-mastg) | Incorporado en el PR 113 | [`e8183038d7a8`](https://github.com/OWASP/mastg/tree/e8183038d7a88c1ac962732d6e3f6e7f40a0251c) |
| 12 | [foundry-rs/foundry](../upstream/012-foundry) | Base funcional del PR 112 | [`20ccce88eeb5`](https://github.com/foundry-rs/foundry/tree/20ccce88eeb5d4d78ed0662699706d6b021a692c) |
| 15 | [ack3-ai/wake](../upstream/015-wake) | Base funcional del PR 112 | [`237d0b02e09e`](https://github.com/ack3-ai/wake/tree/237d0b02e09e0d6bfc5a6ce06cf5e52db04c643b) |
| 24 | [tree-sitter/tree-sitter](../upstream/024-tree-sitter) | Base funcional del PR 112 | [`32594ac6e053`](https://github.com/tree-sitter/tree-sitter/tree/32594ac6e0532a31bcca7fcd043c34ff5e5e007a) |
| 25 | [ast-grep/ast-grep](../upstream/025-ast-grep) | Base funcional del PR 112 | [`8a92260ad4b6`](https://github.com/ast-grep/ast-grep/tree/8a92260ad4b65cf4b716518a76b919e6f0d051b8) |
| 28 | [proptest-rs/proptest](../upstream/028-proptest) | Base funcional del PR 112 | [`70cf37d46b7d`](https://github.com/proptest-rs/proptest/tree/70cf37d46b7d83393b6ed94c611f8c52209f585d) |
| 30 | [OWASP/ASVS](../upstream/030-asvs) | Base funcional del PR 112 | [`82fb2f41cdb6`](https://github.com/OWASP/ASVS/tree/82fb2f41cdb623e0b11e4d9a6b97c4306c1d119c) |
| 35 | [argotorg/solidity](../upstream/035-solidity) | Base funcional del PR 112 | [`bc24c77fb97a`](https://github.com/argotorg/solidity/tree/bc24c77fb97afa3a42955a3762f88dac2ee65170) |
| 36 | [ethereum/execution-specs](../upstream/036-execution-specs) | Base funcional del PR 112 | [`391d8a05d5cb`](https://github.com/ethereum/execution-specs/tree/391d8a05d5cb182542ac7e7330c858b6ee03f990) |
| 41 | [cvc5/cvc5](../upstream/041-cvc5) | Base funcional del PR 112 | [`0782632364f3`](https://github.com/cvc5/cvc5/tree/0782632364f3748b0ccafe2ff3fedcc62917a92c) |
| 43 | [diffblue/cbmc](../upstream/043-cbmc) | Base funcional del PR 112 | [`d29720523b36`](https://github.com/diffblue/cbmc/tree/d29720523b363987a3c5ccf6d4255a813fb8fe47) |
| 44 | [model-checking/kani](../upstream/044-kani) | Base funcional del PR 112 | [`b62331c9d7c2`](https://github.com/model-checking/kani/tree/b62331c9d7c2acc78559f2d2fbfa11b95e4a0fcc) |
| 45 | [tlaplus/tlaplus](../upstream/045-tlaplus) | Base funcional del PR 112 | [`bc1b506bdcad`](https://github.com/tlaplus/tlaplus/tree/bc1b506bdcad80bb518bf3776a9161c34ff0fc4c) |
| 46 | [klee/klee](../upstream/046-klee) | Base funcional del PR 112 | [`a01dff0132ca`](https://github.com/klee/klee/tree/a01dff0132caf705de7678c97af2721a734efdc1) |
| 108 | [pmd/pmd](../upstream/108-pmd) | Base funcional del PR 112 | [`d37763dbd32b`](https://github.com/pmd/pmd/tree/d37763dbd32bc1db21bc849037594631089743f3) |
| 111 | [microsoft/sarif-sdk](../upstream/111-sarif-sdk) | Base funcional del PR 112 | [`724b6a886914`](https://github.com/microsoft/sarif-sdk/tree/724b6a8869142628e2f060115e506f9609a98f73) |
| 120 | [esbmc/esbmc](../upstream/120-esbmc) | Base funcional del PR 112 | [`3194304fbf4e`](https://github.com/esbmc/esbmc/tree/3194304fbf4e75b203e0fc422be31059eb096097) |
| 121 | [seahorn/seahorn](../upstream/121-seahorn) | Base funcional del PR 112 | [`892780176731`](https://github.com/seahorn/seahorn/tree/892780176731ec8e97bbb9f6b172fcacd77a8ff4) |
| 122 | [dafny-lang/dafny](../upstream/122-dafny) | Base funcional del PR 112 | [`8e67e29912aa`](https://github.com/dafny-lang/dafny/tree/8e67e29912aa81b06a8b8e288c7e3046072ea482) |
| 123 | [verus-lang/verus](../upstream/123-verus) | Base funcional del PR 112 | [`cc615f27c3d3`](https://github.com/verus-lang/verus/tree/cc615f27c3d3dec80a83324ed333e48f32d8686c) |
| 124 | [GaloisInc/saw-script](../upstream/124-saw-script) | Base funcional del PR 112 | [`00e03b6050a9`](https://github.com/GaloisInc/saw-script/tree/00e03b6050a9c7f3867bdf27ddc60c81c298fe96) |
| 125 | [rocq-prover/rocq](../upstream/125-rocq) | Base funcional del PR 112 | [`21891774bf01`](https://github.com/rocq-prover/rocq/tree/21891774bf0131945f6cf454e56121d6a4fda02e) |
| 126 | [FStarLang/FStar](../upstream/126-fstar) | Base funcional del PR 112 | [`fc1776afe592`](https://github.com/FStarLang/FStar/tree/fc1776afe592ed8eef352c6610614a70d77b3b66) |
| 127 | [verifast/verifast](../upstream/127-verifast) | Base funcional del PR 112 | [`0a83dba42db7`](https://github.com/verifast/verifast/tree/0a83dba42db7ce0b445034ece5298afe980e57dc) |
| 128 | [AliveToolkit/alive2](../upstream/128-alive2) | Base funcional del PR 112 | [`3bdd4f5e1cef`](https://github.com/AliveToolkit/alive2/tree/3bdd4f5e1cefa47057e93110e707acd11cfe08e4) |
| 131 | [lief-project/LIEF](../upstream/131-lief) | Base funcional del PR 112 | [`2a6fdbc5a3af`](https://github.com/lief-project/LIEF/tree/2a6fdbc5a3af9b7ac797514ca38b1175c78f3fcf) |
| 134 | [qemu/qemu](../upstream/134-qemu) | Base funcional del PR 112 | [`8f66cb79044c`](https://github.com/qemu/qemu/tree/8f66cb79044c370e3813c56ceb7a75a5ca2d0a0e) |
| 135 | [google/osv-scanner](../upstream/135-osv-scanner) | Base funcional del PR 112 | [`84976ca9f198`](https://github.com/google/osv-scanner/tree/84976ca9f19810864f7de74cefb153919f4e663c) |
| 136 | [anchore/syft](../upstream/136-syft) | Base funcional del PR 112 | [`139612f0cc25`](https://github.com/anchore/syft/tree/139612f0cc25952bad472ab8ce6a86e4b442da95) |
| 139 | [DependencyTrack/dependency-track](../upstream/139-dependency-track) | Base funcional del PR 112 | [`f63e6bb18a4e`](https://github.com/DependencyTrack/dependency-track/tree/f63e6bb18a4e1b6e8cca8539b5caf92ff3d93f5d) |
| 140 | [cdxgen/cdxgen](../upstream/140-cdxgen) | Base funcional del PR 112 | [`af131a308eef`](https://github.com/cdxgen/cdxgen/tree/af131a308eef3cfba3cbdee84127a61d1ff6a1a9) |
| 141 | [ossf/scorecard](../upstream/141-scorecard) | Base funcional del PR 112 | [`b62c617675f5`](https://github.com/ossf/scorecard/tree/b62c617675f5dd81ba2bf89a065040559f92f8d7) |
| 142 | [guacsec/guac](../upstream/142-guac) | Base funcional del PR 112 | [`af8abdb5e1a4`](https://github.com/guacsec/guac/tree/af8abdb5e1a4823f7c2afa1b5fddcbba7fc2e98f) |
| 143 | [in-toto/in-toto](../upstream/143-in-toto) | Base funcional del PR 112 | [`e352b43ad7cb`](https://github.com/in-toto/in-toto/tree/e352b43ad7cb8915d84c36d791aa61346152a0a3) |
| 146 | [rustsec/rustsec](../upstream/146-rustsec) | Base funcional del PR 112 | [`a57d1d8c7ad3`](https://github.com/rustsec/rustsec/tree/a57d1d8c7ad3d314a1b6d17243fe3b5c74697739) |
| 147 | [EmbarkStudios/cargo-deny](../upstream/147-cargo-deny) | Base funcional del PR 112 | [`6d512893fcfe`](https://github.com/EmbarkStudios/cargo-deny/tree/6d512893fcfea934e8e69c5df44132a4970c42d0) |
| 150 | [aboutcode-org/scancode-toolkit](../upstream/150-scancode-toolkit) | Base funcional del PR 112 | [`e423b48a1fdb`](https://github.com/aboutcode-org/scancode-toolkit/tree/e423b48a1fdbff26219fbeafe7e9bdef293b91fc) |
| 154 | [langchain-ai/langgraph](../upstream/154-langgraph) | Base funcional del PR 112 | [`c6335a4255dc`](https://github.com/langchain-ai/langgraph/tree/c6335a4255dc1d8abc25a7677f9c072c7ab27b9c) |
| 157 | [deepset-ai/haystack](../upstream/157-haystack) | Base funcional del PR 112 | [`85b8d4e0b833`](https://github.com/deepset-ai/haystack/tree/85b8d4e0b8332a60002c3e06972386476fba6b7a) |
| 158 | [run-llama/llama_index](../upstream/158-llama_index) | Base funcional del PR 112 | [`99d7433f6f71`](https://github.com/run-llama/llama_index/tree/99d7433f6f71888951379ccca9294e272442c832) |
| 159 | [qdrant/qdrant](../upstream/159-qdrant) | Base funcional del PR 112 | [`23065a0bf685`](https://github.com/qdrant/qdrant/tree/23065a0bf6857c3e5da45f6c8939cc746cc0580e) |
| 160 | [pgvector/pgvector](../upstream/160-pgvector) | Base funcional del PR 112 | [`1d56580cda45`](https://github.com/pgvector/pgvector/tree/1d56580cda45d20b6b197fbe325fb0f6301e33cd) |
| 172 | [ethers-io/ethers.js](../upstream/172-ethers.js) | Base funcional del PR 112 | [`3ea4c226dd0b`](https://github.com/ethers-io/ethers.js/tree/3ea4c226dd0b3a074abf90748de9d11192027f4f) |
| 173 | [wevm/viem](../upstream/173-viem) | Base funcional del PR 112 | [`2450e26872b4`](https://github.com/wevm/viem/tree/2450e26872b47aac7dc9f098298c04d2e8d4f374) |
| 174 | [ethereumjs/ethereumjs-monorepo](../upstream/174-ethereumjs-monorepo) | Base funcional del PR 112 | [`11695f6cec3d`](https://github.com/ethereumjs/ethereumjs-monorepo/tree/11695f6cec3d99e143169e51ee91a0b6d146908f) |
| 190 | [ethereum/EIPs](../upstream/190-eips) | Base funcional del PR 112 | [`b4b2ac745e77`](https://github.com/ethereum/EIPs/tree/b4b2ac745e77291d7b47d45665d4e016ab58d31e) |
| 199 | [OWASP/CheatSheetSeries](../upstream/199-cheatsheetseries) | Base funcional del PR 112 | [`c2a1e3e32cec`](https://github.com/OWASP/CheatSheetSeries/tree/c2a1e3e32cec12f27be0a3b1e771ce51288a363e) |

## Las 47 entradas con referencia de catálogo

| ID | Repositorio |
|---:|---|
| 1 | usestrix/strix |
| 2 | zaproxy/zaproxy |
| 3 | sqlmapproject/sqlmap |
| 5 | ffuf/ffuf |
| 6 | projectdiscovery/httpx |
| 7 | projectdiscovery/katana |
| 8 | PortSwigger/turbo-intruder |
| 9 | PortSwigger/param-miner |
| 10 | hahwul/dalfox |
| 11 | projectdiscovery/subfinder |
| 19 | SunWeb3Sec/DeFiHackLabs |
| 21 | immunefi-team/forge-poc-templates |
| 29 | microsoft/restler-fuzzer |
| 51 | s0md3v/Arjun |
| 52 | maurosoria/dirsearch |
| 53 | epi052/feroxbuster |
| 54 | OJ/gobuster |
| 55 | xnl-h4ck3r/xnLinkFinder |
| 56 | xnl-h4ck3r/waymore |
| 58 | projectdiscovery/naabu |
| 60 | d3mondev/puredns |
| 62 | danielmiessler/SecLists |
| 63 | EnableSecurity/wafw00f |
| 64 | lc/gau |
| 67 | wapiti-scanner/wapiti |
| 68 | PortSwigger/http-request-smuggler |
| 70 | doyensec/inql |
| 71 | ticarpi/jwt_tool |
| 73 | dolevf/graphql-cop |
| 74 | dolevf/graphw00f |
| 78 | RhinoSecurityLabs/pacu |
| 79 | BishopFox/cloudfox |
| 81 | DataDog/stratus-red-team |
| 94 | OWASP/Nettacker |
| 96 | MobSF/Mobile-Security-Framework-MobSF |
| 100 | sensepost/objection |
| 169 | NVIDIA/garak |
| 170 | bountybench/bountybench |
| 179 | smartbugs/smartbugs |
| 191 | crytic/building-secure-contracts |
| 192 | theredguild/damn-vulnerable-defi |
| 193 | OpenZeppelin/ethernaut |
| 194 | juice-shop/juice-shop |
| 195 | WebGoat/WebGoat |
| 196 | OWASP/crAPI |
| 197 | digininja/DVWA |
| 198 | vulhub/vulhub |

[Catálogo original de 200](repositories_200.json) · [Procedencia de las 200 identidades](product_supply/upstream-notices.json).
