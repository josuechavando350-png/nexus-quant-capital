# Código fuente directo en NQC · 200 de 200

Las 200 identidades tienen un submódulo directo registrado en `.gitmodules` y en el árbol Git de NQC. Se materializaron y verificaron sus revisiones, índices y archivos rastreados. Los 153 commits anteriores permanecen iguales; se incorporaron las 47 fuentes que faltaban.

| Comprobación | Resultado |
|---|---:|
| Checkouts directos verificados | 200 |
| Checkouts anteriores conservados | 153 |
| Nuevos checkouts | 47 |
| Identidades sólo en catálogo | 0 |
| Gitlinks anidados inventariados | 141 |
| Punteros Git LFS inventariados | 1 |

El alcance es el contenido rastreado por cada Git directo. Los 141 gitlinks anidados y el objeto externo de Git LFS se identificaron por separado; esta entrega no acredita su materialización. Tener fuente incorporada no acredita participación funcional. La [matriz de integración](INTEGRATION_STATUS_200.md) conserva esa distinción.

Los avisos de las 200 identidades se volvieron a procesar con ScanCode 32.5.0. Las observaciones coinciden con la revisión anterior, incluida la resolución del enlace del aviso de viem. Esto no constituye un dictamen completo sobre las obligaciones de redistribución del conjunto ni sobre todas las dependencias transitivas.

## Reproducir el inventario

Desde un checkout de esta rama, descargar los submódulos directos y comprobarlos:

```sh
git submodule update --init --depth 1 --jobs 8
python3.12 -B -m superhunter product-sources --require-checkout --jobs 4
```

La salida debe tener `count: 200`, `catalog_only_count: 0` y `status_counts: {"checked_out": 200}`. El verificador rechaza cambios del índice, archivos rastreados distintos o revisiones diferentes. Sin `--require-checkout` sólo se cotejan las declaraciones fijadas en Git.

[Resultado de los 200 checkouts](product_supply/source-checkouts-200.json) · [Recibo de conservación e incorporación](product_supply/source-completion-200.json) · [Inventario de árboles y avisos](product_supply/source-inventory.json).

La [prueba portable de los 47 commits](OFFLINE_SOURCE_AND_GO.md) permanece como evidencia suplementaria y sigue verificándose; esas identidades ahora también tienen checkout directo.

## Identidades y revisiones

| ID | Repositorio | Incorporación | Commit |
|---:|---|---|---|
| 1 | [usestrix/strix](https://github.com/usestrix/strix) | Nueva | [`a1ccf777d80e`](https://github.com/usestrix/strix/tree/a1ccf777d80e812edf23fc8b82bdc17def6143ac) |
| 2 | [zaproxy/zaproxy](https://github.com/zaproxy/zaproxy) | Nueva | [`42d1450e6ced`](https://github.com/zaproxy/zaproxy/tree/42d1450e6cedc921dae6b4b7103cbe40f8cd98df) |
| 3 | [sqlmapproject/sqlmap](https://github.com/sqlmapproject/sqlmap) | Nueva | [`5db2e62884d9`](https://github.com/sqlmapproject/sqlmap/tree/5db2e62884d91f3ed3b43ec55904737e4051e9d7) |
| 4 | [schemathesis/schemathesis](https://github.com/schemathesis/schemathesis) | Conservada | [`6bf8e2749411`](https://github.com/schemathesis/schemathesis/tree/6bf8e2749411a8d692bdaaad8227a1be0ee3d43f) |
| 5 | [ffuf/ffuf](https://github.com/ffuf/ffuf) | Nueva | [`8d65e0373e5f`](https://github.com/ffuf/ffuf/tree/8d65e0373e5f223530174e5694285af849770078) |
| 6 | [projectdiscovery/httpx](https://github.com/projectdiscovery/httpx) | Nueva | [`200e6ffaac8f`](https://github.com/projectdiscovery/httpx/tree/200e6ffaac8f705cb0770beb6f9cbae303565659) |
| 7 | [projectdiscovery/katana](https://github.com/projectdiscovery/katana) | Nueva | [`732936b3c304`](https://github.com/projectdiscovery/katana/tree/732936b3c3048b5010cb3ddbedf7912cda6ec0ed) |
| 8 | [PortSwigger/turbo-intruder](https://github.com/PortSwigger/turbo-intruder) | Nueva | [`a6c9a4982fb2`](https://github.com/PortSwigger/turbo-intruder/tree/a6c9a4982fb276167edac0797c7ac747ab9a11da) |
| 9 | [PortSwigger/param-miner](https://github.com/PortSwigger/param-miner) | Nueva | [`e43e3b16be11`](https://github.com/PortSwigger/param-miner/tree/e43e3b16be11117ed67cfde60e80acf2e95a4adc) |
| 10 | [hahwul/dalfox](https://github.com/hahwul/dalfox) | Nueva | [`5b523bcd89f5`](https://github.com/hahwul/dalfox/tree/5b523bcd89f5a6f0f6e115f0005b9842438a5de6) |
| 11 | [projectdiscovery/subfinder](https://github.com/projectdiscovery/subfinder) | Nueva | [`e989d248ba90`](https://github.com/projectdiscovery/subfinder/tree/e989d248ba903ced697487f8828a161ef7aa64af) |
| 12 | [foundry-rs/foundry](https://github.com/foundry-rs/foundry) | Conservada | [`20ccce88eeb5`](https://github.com/foundry-rs/foundry/tree/20ccce88eeb5d4d78ed0662699706d6b021a692c) |
| 13 | [crytic/slither](https://github.com/crytic/slither) | Conservada | [`97c1d10d8107`](https://github.com/crytic/slither/tree/97c1d10d8107e76a9426dd484c03c1afd846c186) |
| 14 | [crytic/echidna](https://github.com/crytic/echidna) | Conservada | [`fb0fd78b9c3c`](https://github.com/crytic/echidna/tree/fb0fd78b9c3c46ac4127279da2313e727a66e5ad) |
| 15 | [ack3-ai/wake](https://github.com/ack3-ai/wake) | Conservada | [`237d0b02e09e`](https://github.com/ack3-ai/wake/tree/237d0b02e09e0d6bfc5a6ce06cf5e52db04c643b) |
| 16 | [crytic/medusa](https://github.com/crytic/medusa) | Conservada | [`b86c3bbafb9e`](https://github.com/crytic/medusa/tree/b86c3bbafb9e80f7dcb09533006ecb15dbbbdc98) |
| 17 | [argotorg/hevm](https://github.com/argotorg/hevm) | Conservada | [`87598e81c044`](https://github.com/argotorg/hevm/tree/87598e81c044e2889e4a42e9fd706bd5396448f2) |
| 18 | [crytic/properties](https://github.com/crytic/properties) | Conservada | [`5ea14b813ff2`](https://github.com/crytic/properties/tree/5ea14b813ff296e24b4257ab52a0402360f916f6) |
| 19 | [SunWeb3Sec/DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs) | Nueva | [`18c4aaf35493`](https://github.com/SunWeb3Sec/DeFiHackLabs/tree/18c4aaf3549373b3c0f52dd0ed3e298264dbe1a8) |
| 20 | [shazow/whatsabi](https://github.com/shazow/whatsabi) | Conservada | [`eefa62383640`](https://github.com/shazow/whatsabi/tree/eefa62383640b9056aade49d1d5ed2206ffcdb3b) |
| 21 | [immunefi-team/forge-poc-templates](https://github.com/immunefi-team/forge-poc-templates) | Nueva | [`32f4ccd9049e`](https://github.com/immunefi-team/forge-poc-templates/tree/32f4ccd9049e641cc3723b1e091d33b6b0e8ff34) |
| 22 | [Fraunhofer-AISEC/cpg](https://github.com/Fraunhofer-AISEC/cpg) | Conservada | [`8a4bd21ec859`](https://github.com/Fraunhofer-AISEC/cpg/tree/8a4bd21ec8591b1bc92ca6174a01ab5159514e09) |
| 23 | [meta/Pysa](https://github.com/meta/Pysa) | Conservada | [`50ba6ccf2612`](https://github.com/meta/Pysa/tree/50ba6ccf2612131033662e0a6bc5e8acffc6ff36) |
| 24 | [tree-sitter/tree-sitter](https://github.com/tree-sitter/tree-sitter) | Conservada | [`32594ac6e053`](https://github.com/tree-sitter/tree-sitter/tree/32594ac6e0532a31bcca7fcd043c34ff5e5e007a) |
| 25 | [ast-grep/ast-grep](https://github.com/ast-grep/ast-grep) | Conservada | [`8a92260ad4b6`](https://github.com/ast-grep/ast-grep/tree/8a92260ad4b65cf4b716518a76b919e6f0d051b8) |
| 26 | [mitmproxy/mitmproxy](https://github.com/mitmproxy/mitmproxy) | Conservada | [`c491986978a6`](https://github.com/mitmproxy/mitmproxy/tree/c491986978a6280c29977482cb18698d6523a662) |
| 27 | [microsoft/playwright](https://github.com/microsoft/playwright) | Conservada | [`049226728d2d`](https://github.com/microsoft/playwright/tree/049226728d2da8054db18b04782a9848b755855e) |
| 28 | [proptest-rs/proptest](https://github.com/proptest-rs/proptest) | Conservada | [`70cf37d46b7d`](https://github.com/proptest-rs/proptest/tree/70cf37d46b7d83393b6ed94c611f8c52209f585d) |
| 29 | [microsoft/restler-fuzzer](https://github.com/microsoft/restler-fuzzer) | Nueva | [`6d984deedbc5`](https://github.com/microsoft/restler-fuzzer/tree/6d984deedbc54aad957fa3da0c7e9e5df23a2aee) |
| 30 | [OWASP/ASVS](https://github.com/OWASP/ASVS) | Conservada | [`82fb2f41cdb6`](https://github.com/OWASP/ASVS/tree/82fb2f41cdb623e0b11e4d9a6b97c4306c1d119c) |
| 31 | [runtimeverification/evm-semantics](https://github.com/runtimeverification/evm-semantics) | Conservada | [`fbb2edbb8e84`](https://github.com/runtimeverification/evm-semantics/tree/fbb2edbb8e84bb05b6ba7a255ce1f44f76051ad1) |
| 32 | [trailofbits/mewt](https://github.com/trailofbits/mewt) | Conservada | [`e96e71969ae9`](https://github.com/trailofbits/mewt/tree/e96e71969ae9b9d3ef7562ae5a3a60de6050c0d0) |
| 33 | [Jon-Becker/heimdall-rs](https://github.com/Jon-Becker/heimdall-rs) | Conservada | [`89e107f033f6`](https://github.com/Jon-Becker/heimdall-rs/tree/89e107f033f6e8fc037ba58757ac855e2a7049dd) |
| 34 | [cdump/evmole](https://github.com/cdump/evmole) | Conservada | [`763f2984f6be`](https://github.com/cdump/evmole/tree/763f2984f6be5ea33636336e804022c75318a260) |
| 35 | [argotorg/solidity](https://github.com/argotorg/solidity) | Conservada | [`bc24c77fb97a`](https://github.com/argotorg/solidity/tree/bc24c77fb97afa3a42955a3762f88dac2ee65170) |
| 36 | [ethereum/execution-specs](https://github.com/ethereum/execution-specs) | Conservada | [`391d8a05d5cb`](https://github.com/ethereum/execution-specs/tree/391d8a05d5cb182542ac7e7330c858b6ee03f990) |
| 37 | [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) | Conservada | [`2b7829ea6aed`](https://github.com/ethereum/go-ethereum/tree/2b7829ea6aed9a95a3fd793cca46731202c6c310) |
| 38 | [bluealloy/revm](https://github.com/bluealloy/revm) | Conservada | [`61eb0f231227`](https://github.com/bluealloy/revm/tree/61eb0f231227db0a89f9cd2cd976cc372b6e94d1) |
| 39 | [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) | Conservada | [`5172e1681f05`](https://github.com/OpenZeppelin/openzeppelin-contracts/tree/5172e1681f05f4aa189b7740bf2c0316af67c3b3) |
| 40 | [OpenZeppelin/openzeppelin-upgrades](https://github.com/OpenZeppelin/openzeppelin-upgrades) | Conservada | [`54bb8bb913c2`](https://github.com/OpenZeppelin/openzeppelin-upgrades/tree/54bb8bb913c2d52f417d3bcf1ef94e9061b89da8) |
| 41 | [cvc5/cvc5](https://github.com/cvc5/cvc5) | Conservada | [`0782632364f3`](https://github.com/cvc5/cvc5/tree/0782632364f3748b0ccafe2ff3fedcc62917a92c) |
| 42 | [AFLplusplus/AFLplusplus](https://github.com/AFLplusplus/AFLplusplus) | Conservada | [`d798677805de`](https://github.com/AFLplusplus/AFLplusplus/tree/d798677805de81b50aa8f45beb0342ae1617b9d8) |
| 43 | [diffblue/cbmc](https://github.com/diffblue/cbmc) | Conservada | [`d29720523b36`](https://github.com/diffblue/cbmc/tree/d29720523b363987a3c5ccf6d4255a813fb8fe47) |
| 44 | [model-checking/kani](https://github.com/model-checking/kani) | Conservada | [`b62331c9d7c2`](https://github.com/model-checking/kani/tree/b62331c9d7c2acc78559f2d2fbfa11b95e4a0fcc) |
| 45 | [tlaplus/tlaplus](https://github.com/tlaplus/tlaplus) | Conservada | [`bc1b506bdcad`](https://github.com/tlaplus/tlaplus/tree/bc1b506bdcad80bb518bf3776a9161c34ff0fc4c) |
| 46 | [klee/klee](https://github.com/klee/klee) | Conservada | [`a01dff0132ca`](https://github.com/klee/klee/tree/a01dff0132caf705de7678c97af2721a734efdc1) |
| 47 | [rr-debugger/rr](https://github.com/rr-debugger/rr) | Conservada | [`f5017a5cea71`](https://github.com/rr-debugger/rr/tree/f5017a5cea712d4958ca72edefd92a0401649bee) |
| 48 | [jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) | Conservada | [`f9046f3dadd6`](https://github.com/jaegertracing/jaeger/tree/f9046f3dadd6778e0b2995bc6b41fdf35f9381b1) |
| 49 | [OWASP/wstg](https://github.com/OWASP/wstg) | Conservada | [`97d915fa54f0`](https://github.com/OWASP/wstg/tree/97d915fa54f0c21b99094acdc5af677be3dc780f) |
| 50 | [strace/strace](https://github.com/strace/strace) | Conservada | [`ec439c5485b2`](https://github.com/strace/strace/tree/ec439c5485b234228c1d07a9daf111dafadde75c) |
| 51 | [s0md3v/Arjun](https://github.com/s0md3v/Arjun) | Nueva | [`d1fb995cb1e0`](https://github.com/s0md3v/Arjun/tree/d1fb995cb1e064d4e171d83f19f6af79b0a3c5ce) |
| 52 | [maurosoria/dirsearch](https://github.com/maurosoria/dirsearch) | Nueva | [`461705af2688`](https://github.com/maurosoria/dirsearch/tree/461705af2688ab6644b1f2bf738c46c55ee4d3da) |
| 53 | [epi052/feroxbuster](https://github.com/epi052/feroxbuster) | Nueva | [`f89b6c6d3054`](https://github.com/epi052/feroxbuster/tree/f89b6c6d305421d7b29e26997960317e64c64dae) |
| 54 | [OJ/gobuster](https://github.com/OJ/gobuster) | Nueva | [`c77583fbb882`](https://github.com/OJ/gobuster/tree/c77583fbb8824058d74d38240896eff610683c8e) |
| 55 | [xnl-h4ck3r/xnLinkFinder](https://github.com/xnl-h4ck3r/xnLinkFinder) | Nueva | [`841ac8dddbc7`](https://github.com/xnl-h4ck3r/xnLinkFinder/tree/841ac8dddbc7edd728939df5db51274a63ab5863) |
| 56 | [xnl-h4ck3r/waymore](https://github.com/xnl-h4ck3r/waymore) | Nueva | [`4e02de512fd6`](https://github.com/xnl-h4ck3r/waymore/tree/4e02de512fd6b110be92dc8bffb3002edfebcb6c) |
| 57 | [projectdiscovery/dnsx](https://github.com/projectdiscovery/dnsx) | Conservada | [`f98967b41787`](https://github.com/projectdiscovery/dnsx/tree/f98967b4178790e5a3654c5d9c822dc3544db793) |
| 58 | [projectdiscovery/naabu](https://github.com/projectdiscovery/naabu) | Nueva | [`d74d055f7e0e`](https://github.com/projectdiscovery/naabu/tree/d74d055f7e0e508c90670c46bb3e1bb16fd16c26) |
| 59 | [projectdiscovery/tlsx](https://github.com/projectdiscovery/tlsx) | Conservada | [`53e3d20a14f9`](https://github.com/projectdiscovery/tlsx/tree/53e3d20a14f917e423c970b4db2944a202e6549a) |
| 60 | [d3mondev/puredns](https://github.com/d3mondev/puredns) | Nueva | [`46bd4c963ec2`](https://github.com/d3mondev/puredns/tree/46bd4c963ec2b28c5241c03c161bdc41bb93fdc0) |
| 61 | [blechschmidt/massdns](https://github.com/blechschmidt/massdns) | Conservada | [`30c380908b4f`](https://github.com/blechschmidt/massdns/tree/30c380908b4f9afd0931d3d83f85884844831846) |
| 62 | [danielmiessler/SecLists](https://github.com/danielmiessler/SecLists) | Nueva | [`64e7d0b91001`](https://github.com/danielmiessler/SecLists/tree/64e7d0b910015fa4e8dffa9fed7aba7d73e4673d) |
| 63 | [EnableSecurity/wafw00f](https://github.com/EnableSecurity/wafw00f) | Nueva | [`69fbe3956bba`](https://github.com/EnableSecurity/wafw00f/tree/69fbe3956bba47a172cf87e40e9037535d32a130) |
| 64 | [lc/gau](https://github.com/lc/gau) | Nueva | [`4eabace30987`](https://github.com/lc/gau/tree/4eabace309877abb231def9eeb27b96c07ed3635) |
| 65 | [rapid7/recog](https://github.com/rapid7/recog) | Conservada | [`f1191e24332c`](https://github.com/rapid7/recog/tree/f1191e24332c51d6a3d98457f64fba8dec340784) |
| 66 | [nabla-c0d3/sslyze](https://github.com/nabla-c0d3/sslyze) | Conservada | [`e064c2c8e7d2`](https://github.com/nabla-c0d3/sslyze/tree/e064c2c8e7d251e5bc5db1a7beb21add5e12a0bc) |
| 67 | [wapiti-scanner/wapiti](https://github.com/wapiti-scanner/wapiti) | Nueva | [`e786fdb0e4b5`](https://github.com/wapiti-scanner/wapiti/tree/e786fdb0e4b581e501e1a04c27f2e59eb41bdbbb) |
| 68 | [PortSwigger/http-request-smuggler](https://github.com/PortSwigger/http-request-smuggler) | Nueva | [`3ecb1afa6a1d`](https://github.com/PortSwigger/http-request-smuggler/tree/3ecb1afa6a1d21ef1ec4e6eb1337818b53a2b4c0) |
| 69 | [fullstorydev/grpcurl](https://github.com/fullstorydev/grpcurl) | Conservada | [`f5c25e012bd4`](https://github.com/fullstorydev/grpcurl/tree/f5c25e012bd451b55444679d5457ed3dfbae53de) |
| 70 | [doyensec/inql](https://github.com/doyensec/inql) | Nueva | [`b1aae1502a1d`](https://github.com/doyensec/inql/tree/b1aae1502a1d2469f8d4160b88238dd450ba5982) |
| 71 | [ticarpi/jwt_tool](https://github.com/ticarpi/jwt_tool) | Nueva | [`3bc7407cf222`](https://github.com/ticarpi/jwt_tool/tree/3bc7407cf2222d6a821dcc19c776e5a1b1cb9a9b) |
| 72 | [testssl/testssl.sh](https://github.com/testssl/testssl.sh) | Conservada | [`0f87aca237ae`](https://github.com/testssl/testssl.sh/tree/0f87aca237ae52a35e69a14157c37377a1779908) |
| 73 | [dolevf/graphql-cop](https://github.com/dolevf/graphql-cop) | Nueva | [`2b7e086efae6`](https://github.com/dolevf/graphql-cop/tree/2b7e086efae672f28b419c7fcdfe6b48d846c9dc) |
| 74 | [dolevf/graphw00f](https://github.com/dolevf/graphw00f) | Nueva | [`4901f824140a`](https://github.com/dolevf/graphw00f/tree/4901f824140a2da168876412593c213afbdd75fb) |
| 75 | [prowler-cloud/prowler](https://github.com/prowler-cloud/prowler) | Conservada | [`02d631d3a5db`](https://github.com/prowler-cloud/prowler/tree/02d631d3a5db2c8676e9703aec286c7723a32e6f) |
| 76 | [kubescape/kubescape](https://github.com/kubescape/kubescape) | Conservada | [`ef4faa945647`](https://github.com/kubescape/kubescape/tree/ef4faa945647cdd735f6aa3346567092f51c3a6a) |
| 77 | [aquasecurity/kube-bench](https://github.com/aquasecurity/kube-bench) | Conservada | [`e278a5915a98`](https://github.com/aquasecurity/kube-bench/tree/e278a5915a982f2756026de6e2f9ca77077ef9f9) |
| 78 | [RhinoSecurityLabs/pacu](https://github.com/RhinoSecurityLabs/pacu) | Nueva | [`7dd34aa0856b`](https://github.com/RhinoSecurityLabs/pacu/tree/7dd34aa0856b2a964763a70be9dc9d78abc08a81) |
| 79 | [BishopFox/cloudfox](https://github.com/BishopFox/cloudfox) | Nueva | [`f65be085cde3`](https://github.com/BishopFox/cloudfox/tree/f65be085cde3768281c2dbafc57542a56ee12ebe) |
| 80 | [cartography-cncf/cartography](https://github.com/cartography-cncf/cartography) | Conservada | [`ce236e196bbe`](https://github.com/cartography-cncf/cartography/tree/ce236e196bbec30c99502e6ff5ac809a23b2ec42) |
| 81 | [DataDog/stratus-red-team](https://github.com/DataDog/stratus-red-team) | Nueva | [`dea75a460718`](https://github.com/DataDog/stratus-red-team/tree/dea75a460718e632e90d98093f982b64f9e60c02) |
| 82 | [stackrox/kube-linter](https://github.com/stackrox/kube-linter) | Conservada | [`85cdcb9843fe`](https://github.com/stackrox/kube-linter/tree/85cdcb9843fe07f0bf7d82026de0e79e4b517576) |
| 83 | [cilium/cilium](https://github.com/cilium/cilium) | Conservada | [`fb070362cec9`](https://github.com/cilium/cilium/tree/fb070362cec985b65e10d733365b1f34839dbf5b) |
| 84 | [iann0036/iamlive](https://github.com/iann0036/iamlive) | Conservada | [`3ec1a40e560c`](https://github.com/iann0036/iamlive/tree/3ec1a40e560c2f00ec82c50223add810e2567efb) |
| 85 | [salesforce/policy_sentry](https://github.com/salesforce/policy_sentry) | Conservada | [`2575f2b873e1`](https://github.com/salesforce/policy_sentry/tree/2575f2b873e1c1f0fb604a448dee392f39ad74ad) |
| 86 | [falcosecurity/falco](https://github.com/falcosecurity/falco) | Conservada | [`74ccf76b7b2d`](https://github.com/falcosecurity/falco/tree/74ccf76b7b2d85ff42c97da6bd6a716b0d1d17b9) |
| 87 | [aquasecurity/tracee](https://github.com/aquasecurity/tracee) | Conservada | [`2f9dc40c20b1`](https://github.com/aquasecurity/tracee/tree/2f9dc40c20b17c2ba27f6d92b25e62790bd48a62) |
| 88 | [cilium/tetragon](https://github.com/cilium/tetragon) | Conservada | [`951e79711c67`](https://github.com/cilium/tetragon/tree/951e79711c673ac932528b535471f895cd8b0094) |
| 89 | [cilium/hubble](https://github.com/cilium/hubble) | Conservada | [`35bf8033a880`](https://github.com/cilium/hubble/tree/35bf8033a880ac9b04bd0499067615de4815585b) |
| 90 | [inspektor-gadget/inspektor-gadget](https://github.com/inspektor-gadget/inspektor-gadget) | Conservada | [`24db8bae213b`](https://github.com/inspektor-gadget/inspektor-gadget/tree/24db8bae213b56a0f8f9ed915e607cc8aed1dc31) |
| 91 | [wireshark/wireshark](https://github.com/wireshark/wireshark) | Conservada | [`227644216631`](https://github.com/wireshark/wireshark/tree/2276442166317e2d80346cf0eb2f2744dd17c6c2) |
| 92 | [secdev/scapy](https://github.com/secdev/scapy) | Conservada | [`3813c08c414a`](https://github.com/secdev/scapy/tree/3813c08c414a30c686136e50c6e80dd9b3b29663) |
| 93 | [OISF/suricata](https://github.com/OISF/suricata) | Conservada | [`5c7787ed61ad`](https://github.com/OISF/suricata/tree/5c7787ed61adb1aa7a26c23e093992350fc97d62) |
| 94 | [OWASP/Nettacker](https://github.com/OWASP/Nettacker) | Nueva | [`6e04aa1f9cf2`](https://github.com/OWASP/Nettacker/tree/6e04aa1f9cf29b35cae5ba1bb5043fd7b9b651b5) |
| 95 | [the-tcpdump-group/tcpdump](https://github.com/the-tcpdump-group/tcpdump) | Conservada | [`3541bd5d3863`](https://github.com/the-tcpdump-group/tcpdump/tree/3541bd5d38635e208d7dd47cc6ea2af00dd7ef0c) |
| 96 | [MobSF/Mobile-Security-Framework-MobSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF) | Nueva | [`fa87c37892b2`](https://github.com/MobSF/Mobile-Security-Framework-MobSF/tree/fa87c37892b264cf76bed8c358cc2d5d5323c8c2) |
| 97 | [frida/frida](https://github.com/frida/frida) | Conservada | [`a93582c832d7`](https://github.com/frida/frida/tree/a93582c832d74de1eaa0ec59994365f6981368db) |
| 98 | [skylot/jadx](https://github.com/skylot/jadx) | Conservada | [`3cbbc2348141`](https://github.com/skylot/jadx/tree/3cbbc2348141b7b51dbec2b227f334d6785547e6) |
| 99 | [iBotPeaches/Apktool](https://github.com/iBotPeaches/Apktool) | Conservada | [`fbaeb4779d7a`](https://github.com/iBotPeaches/Apktool/tree/fbaeb4779d7aaed2c3097cd496de2bc9150ab869) |
| 100 | [sensepost/objection](https://github.com/sensepost/objection) | Nueva | [`3ef6f9bdcd64`](https://github.com/sensepost/objection/tree/3ef6f9bdcd64c6181a1b01eb11104b7204ec6308) |
| 101 | [meta/infer](https://github.com/meta/infer) | Conservada | [`2ebceff7ce3c`](https://github.com/meta/infer/tree/2ebceff7ce3c93480bbc0e8d09d11aeec53595d8) |
| 102 | [Ericsson/codechecker](https://github.com/Ericsson/codechecker) | Conservada | [`53222cd5d756`](https://github.com/Ericsson/codechecker/tree/53222cd5d7566c553d8d7edbb5134a35a56ef15e) |
| 103 | [cppcheck-opensource/cppcheck](https://github.com/cppcheck-opensource/cppcheck) | Conservada | [`e1b5791564c6`](https://github.com/cppcheck-opensource/cppcheck/tree/e1b5791564c662c7dacbc62835f6abe5431aa00b) |
| 104 | [PyCQA/bandit](https://github.com/PyCQA/bandit) | Conservada | [`2d5467c45c31`](https://github.com/PyCQA/bandit/tree/2d5467c45c3189f4d7d07e8022276bc73a478abd) |
| 105 | [securego/gosec](https://github.com/securego/gosec) | Conservada | [`244f1f6f4d1d`](https://github.com/securego/gosec/tree/244f1f6f4d1d0d14f89e79a73dab1219eabb5228) |
| 106 | [phpstan/phpstan](https://github.com/phpstan/phpstan) | Conservada | [`043348b55e6c`](https://github.com/phpstan/phpstan/tree/043348b55e6c54effbdc0cd2f86173bc00ddd0c2) |
| 107 | [vimeo/psalm](https://github.com/vimeo/psalm) | Conservada | [`2da2040e23d8`](https://github.com/vimeo/psalm/tree/2da2040e23d8b54e61be22618bd53517b6bd43df) |
| 108 | [pmd/pmd](https://github.com/pmd/pmd) | Conservada | [`d37763dbd32b`](https://github.com/pmd/pmd/tree/d37763dbd32bc1db21bc849037594631089743f3) |
| 109 | [spotbugs/spotbugs](https://github.com/spotbugs/spotbugs) | Conservada | [`f4544188eb47`](https://github.com/spotbugs/spotbugs/tree/f4544188eb473d60221572fc0d5645325c8b18eb) |
| 110 | [find-sec-bugs/find-sec-bugs](https://github.com/find-sec-bugs/find-sec-bugs) | Conservada | [`aa1293a6339a`](https://github.com/find-sec-bugs/find-sec-bugs/tree/aa1293a6339a04ddf954670fc550847d1bcd83be) |
| 111 | [microsoft/sarif-sdk](https://github.com/microsoft/sarif-sdk) | Conservada | [`724b6a886914`](https://github.com/microsoft/sarif-sdk/tree/724b6a8869142628e2f060115e506f9609a98f73) |
| 112 | [google/honggfuzz](https://github.com/google/honggfuzz) | Conservada | [`940b958dfeb6`](https://github.com/google/honggfuzz/tree/940b958dfeb6f9131fd846cae31fcc0fe996ae98) |
| 113 | [CodeIntelligenceTesting/jazzer](https://github.com/CodeIntelligenceTesting/jazzer) | Conservada | [`bdebf95c4de0`](https://github.com/CodeIntelligenceTesting/jazzer/tree/bdebf95c4de0154f7e6f1666a64d2b951b4a6861) |
| 114 | [google/atheris](https://github.com/google/atheris) | Conservada | [`e36da74cf42b`](https://github.com/google/atheris/tree/e36da74cf42b5834c4e31d7cabb58d796695d29f) |
| 115 | [rust-fuzz/cargo-fuzz](https://github.com/rust-fuzz/cargo-fuzz) | Conservada | [`bf2fc668dafd`](https://github.com/rust-fuzz/cargo-fuzz/tree/bf2fc668dafda5295aa6fd01825ee67b885f0f2b) |
| 116 | [google/fuzztest](https://github.com/google/fuzztest) | Conservada | [`29e1c6a0fc14`](https://github.com/google/fuzztest/tree/29e1c6a0fc149dc108dfff122bd6aac5efbe85b5) |
| 117 | [google/oss-fuzz](https://github.com/google/oss-fuzz) | Conservada | [`48099ac8ad84`](https://github.com/google/oss-fuzz/tree/48099ac8ad840c31d745f6e2a7627195481cb1df) |
| 118 | [trailofbits/polytracker](https://github.com/trailofbits/polytracker) | Conservada | [`ae7b5f12e608`](https://github.com/trailofbits/polytracker/tree/ae7b5f12e608f0c9a896cf1af797e4588c7624f9) |
| 119 | [google/clusterfuzzlite](https://github.com/google/clusterfuzzlite) | Conservada | [`52ecc61cb587`](https://github.com/google/clusterfuzzlite/tree/52ecc61cb587ee99c26825a112a21abf19c7448c) |
| 120 | [esbmc/esbmc](https://github.com/esbmc/esbmc) | Conservada | [`3194304fbf4e`](https://github.com/esbmc/esbmc/tree/3194304fbf4e75b203e0fc422be31059eb096097) |
| 121 | [seahorn/seahorn](https://github.com/seahorn/seahorn) | Conservada | [`892780176731`](https://github.com/seahorn/seahorn/tree/892780176731ec8e97bbb9f6b172fcacd77a8ff4) |
| 122 | [dafny-lang/dafny](https://github.com/dafny-lang/dafny) | Conservada | [`8e67e29912aa`](https://github.com/dafny-lang/dafny/tree/8e67e29912aa81b06a8b8e288c7e3046072ea482) |
| 123 | [verus-lang/verus](https://github.com/verus-lang/verus) | Conservada | [`cc615f27c3d3`](https://github.com/verus-lang/verus/tree/cc615f27c3d3dec80a83324ed333e48f32d8686c) |
| 124 | [GaloisInc/saw-script](https://github.com/GaloisInc/saw-script) | Conservada | [`00e03b6050a9`](https://github.com/GaloisInc/saw-script/tree/00e03b6050a9c7f3867bdf27ddc60c81c298fe96) |
| 125 | [rocq-prover/rocq](https://github.com/rocq-prover/rocq) | Conservada | [`21891774bf01`](https://github.com/rocq-prover/rocq/tree/21891774bf0131945f6cf454e56121d6a4fda02e) |
| 126 | [FStarLang/FStar](https://github.com/FStarLang/FStar) | Conservada | [`fc1776afe592`](https://github.com/FStarLang/FStar/tree/fc1776afe592ed8eef352c6610614a70d77b3b66) |
| 127 | [verifast/verifast](https://github.com/verifast/verifast) | Conservada | [`0a83dba42db7`](https://github.com/verifast/verifast/tree/0a83dba42db7ce0b445034ece5298afe980e57dc) |
| 128 | [AliveToolkit/alive2](https://github.com/AliveToolkit/alive2) | Conservada | [`3bdd4f5e1cef`](https://github.com/AliveToolkit/alive2/tree/3bdd4f5e1cefa47057e93110e707acd11cfe08e4) |
| 129 | [radareorg/radare2](https://github.com/radareorg/radare2) | Conservada | [`3f321aa3aeda`](https://github.com/radareorg/radare2/tree/3f321aa3aeda3a69fa12b1df9840648c31b4df14) |
| 130 | [rizinorg/cutter](https://github.com/rizinorg/cutter) | Conservada | [`d885514bd809`](https://github.com/rizinorg/cutter/tree/d885514bd8092776429a6ed5213b125c17092c77) |
| 131 | [lief-project/LIEF](https://github.com/lief-project/LIEF) | Conservada | [`2a6fdbc5a3af`](https://github.com/lief-project/LIEF/tree/2a6fdbc5a3af9b7ac797514ca38b1175c78f3fcf) |
| 132 | [capstone-engine/capstone](https://github.com/capstone-engine/capstone) | Conservada | [`ccd25ab39eea`](https://github.com/capstone-engine/capstone/tree/ccd25ab39eea534afbb70cfb047310c5a9962553) |
| 133 | [DynamoRIO/dynamorio](https://github.com/DynamoRIO/dynamorio) | Conservada | [`0fd459d944cb`](https://github.com/DynamoRIO/dynamorio/tree/0fd459d944cb13056c7f29eba1d593a637bf3b68) |
| 134 | [qemu/qemu](https://github.com/qemu/qemu) | Conservada | [`8f66cb79044c`](https://github.com/qemu/qemu/tree/8f66cb79044c370e3813c56ceb7a75a5ca2d0a0e) |
| 135 | [google/osv-scanner](https://github.com/google/osv-scanner) | Conservada | [`84976ca9f198`](https://github.com/google/osv-scanner/tree/84976ca9f19810864f7de74cefb153919f4e663c) |
| 136 | [anchore/syft](https://github.com/anchore/syft) | Conservada | [`139612f0cc25`](https://github.com/anchore/syft/tree/139612f0cc25952bad472ab8ce6a86e4b442da95) |
| 137 | [anchore/grype](https://github.com/anchore/grype) | Conservada | [`8b2987cf575c`](https://github.com/anchore/grype/tree/8b2987cf575c69fb715ae4d3b15bb470e3e8f83b) |
| 138 | [dependency-check/DependencyCheck](https://github.com/dependency-check/DependencyCheck) | Conservada | [`ae861fc07f84`](https://github.com/dependency-check/DependencyCheck/tree/ae861fc07f84e3d0be75c2ed2e46b498bc03bcc1) |
| 139 | [DependencyTrack/dependency-track](https://github.com/DependencyTrack/dependency-track) | Conservada | [`f63e6bb18a4e`](https://github.com/DependencyTrack/dependency-track/tree/f63e6bb18a4e1b6e8cca8539b5caf92ff3d93f5d) |
| 140 | [cdxgen/cdxgen](https://github.com/cdxgen/cdxgen) | Conservada | [`af131a308eef`](https://github.com/cdxgen/cdxgen/tree/af131a308eef3cfba3cbdee84127a61d1ff6a1a9) |
| 141 | [ossf/scorecard](https://github.com/ossf/scorecard) | Conservada | [`b62c617675f5`](https://github.com/ossf/scorecard/tree/b62c617675f5dd81ba2bf89a065040559f92f8d7) |
| 142 | [guacsec/guac](https://github.com/guacsec/guac) | Conservada | [`af8abdb5e1a4`](https://github.com/guacsec/guac/tree/af8abdb5e1a4823f7c2afa1b5fddcbba7fc2e98f) |
| 143 | [in-toto/in-toto](https://github.com/in-toto/in-toto) | Conservada | [`e352b43ad7cb`](https://github.com/in-toto/in-toto/tree/e352b43ad7cb8915d84c36d791aa61346152a0a3) |
| 144 | [ossf/package-analysis](https://github.com/ossf/package-analysis) | Conservada | [`a149a6f2e117`](https://github.com/ossf/package-analysis/tree/a149a6f2e1179b8f0c05da6845d8513d360e3b1a) |
| 145 | [ossf/malicious-packages](https://github.com/ossf/malicious-packages) | Conservada | [`aaefca1f03b5`](https://github.com/ossf/malicious-packages/tree/aaefca1f03b51a4e26db1fad48b172279a2e41a9) |
| 146 | [rustsec/rustsec](https://github.com/rustsec/rustsec) | Conservada | [`a57d1d8c7ad3`](https://github.com/rustsec/rustsec/tree/a57d1d8c7ad3d314a1b6d17243fe3b5c74697739) |
| 147 | [EmbarkStudios/cargo-deny](https://github.com/EmbarkStudios/cargo-deny) | Conservada | [`6d512893fcfe`](https://github.com/EmbarkStudios/cargo-deny/tree/6d512893fcfea934e8e69c5df44132a4970c42d0) |
| 148 | [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | Conservada | [`4ef51f69ca63`](https://github.com/trufflesecurity/trufflehog/tree/4ef51f69ca6347aaa76a5e64a87eac9c0c909f71) |
| 149 | [betterleaks/betterleaks](https://github.com/betterleaks/betterleaks) | Conservada | [`4cd708016003`](https://github.com/betterleaks/betterleaks/tree/4cd7080160031ba1c91fd3a58609f4a63af23de1) |
| 150 | [aboutcode-org/scancode-toolkit](https://github.com/aboutcode-org/scancode-toolkit) | Conservada | [`e423b48a1fdb`](https://github.com/aboutcode-org/scancode-toolkit/tree/e423b48a1fdbff26219fbeafe7e9bdef293b91fc) |
| 151 | [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) | Conservada | [`3a893a1b26de`](https://github.com/OpenHands/software-agent-sdk/tree/3a893a1b26de7ec02cc0dd2427906eea6aea3fc7) |
| 152 | [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | Conservada | [`04d809ceab9d`](https://github.com/SWE-agent/mini-swe-agent/tree/04d809ceab9df28f9adaed044884180159172930) |
| 153 | [Aider-AI/aider](https://github.com/Aider-AI/aider) | Conservada | [`5dc9490bb35f`](https://github.com/Aider-AI/aider/tree/5dc9490bb35f9729ef2c95d00a19ccd30c26339c) |
| 154 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Conservada | [`c6335a4255dc`](https://github.com/langchain-ai/langgraph/tree/c6335a4255dc1d8abc25a7677f9c072c7ab27b9c) |
| 155 | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | Conservada | [`226d534da38a`](https://github.com/stanfordnlp/dspy/tree/226d534da38ab8a39e4d6383e01e121dab50da51) |
| 156 | [huggingface/smolagents](https://github.com/huggingface/smolagents) | Conservada | [`99721bdc3b6f`](https://github.com/huggingface/smolagents/tree/99721bdc3b6f502108751a93c5d7f08b1a04ce76) |
| 157 | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | Conservada | [`85b8d4e0b833`](https://github.com/deepset-ai/haystack/tree/85b8d4e0b8332a60002c3e06972386476fba6b7a) |
| 158 | [run-llama/llama_index](https://github.com/run-llama/llama_index) | Conservada | [`99d7433f6f71`](https://github.com/run-llama/llama_index/tree/99d7433f6f71888951379ccca9294e272442c832) |
| 159 | [qdrant/qdrant](https://github.com/qdrant/qdrant) | Conservada | [`23065a0bf685`](https://github.com/qdrant/qdrant/tree/23065a0bf6857c3e5da45f6c8939cc746cc0580e) |
| 160 | [pgvector/pgvector](https://github.com/pgvector/pgvector) | Conservada | [`1d56580cda45`](https://github.com/pgvector/pgvector/tree/1d56580cda45d20b6b197fbe325fb0f6301e33cd) |
| 161 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | Conservada | [`1bdc437402d6`](https://github.com/vllm-project/vllm/tree/1bdc437402d6eee29d3ca543c91574f8acc72c8d) |
| 162 | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | Conservada | [`e6d624b9a4b9`](https://github.com/ggml-org/llama.cpp/tree/e6d624b9a4b95c6b52f5ca384d70b75581f9821a) |
| 163 | [sgl-project/sglang](https://github.com/sgl-project/sglang) | Conservada | [`4ce41378f96d`](https://github.com/sgl-project/sglang/tree/4ce41378f96da24f12e76eae35dfea5bbf35844a) |
| 164 | [huggingface/transformers](https://github.com/huggingface/transformers) | Conservada | [`2f1bc5e321b9`](https://github.com/huggingface/transformers/tree/2f1bc5e321b9a736200a590d6e7743ccdeb60772) |
| 165 | [langfuse/langfuse](https://github.com/langfuse/langfuse) | Conservada | [`306cdfb8b38a`](https://github.com/langfuse/langfuse/tree/306cdfb8b38ac8ca35b9c09cebbf2cd110d06978) |
| 166 | [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) | Conservada | [`8c63f10d500c`](https://github.com/vibrantlabsai/ragas/tree/8c63f10d500c44efbf24fdb9e2920de2104c321c) |
| 167 | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | Conservada | [`b1aca6657b8d`](https://github.com/promptfoo/promptfoo/tree/b1aca6657b8d7353815e78a9bd35273ddcd3fccc) |
| 168 | [UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai) | Conservada | [`82925564c933`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/82925564c9330e5440d490a7d97d037e11e66c9a) |
| 169 | [NVIDIA/garak](https://github.com/NVIDIA/garak) | Nueva | [`725160beb813`](https://github.com/NVIDIA/garak/tree/725160beb8137a8294c79b1f78c68a756367f861) |
| 170 | [bountybench/bountybench](https://github.com/bountybench/bountybench) | Nueva | [`8ece6aab0b95`](https://github.com/bountybench/bountybench/tree/8ece6aab0b954f7c85b5705e69f0142eeaf2c5d1) |
| 171 | [NomicFoundation/hardhat](https://github.com/NomicFoundation/hardhat) | Conservada | [`c6a0b31a8bcb`](https://github.com/NomicFoundation/hardhat/tree/c6a0b31a8bcbb839aa2051f700476e2019e5529d) |
| 172 | [ethers-io/ethers.js](https://github.com/ethers-io/ethers.js) | Conservada | [`3ea4c226dd0b`](https://github.com/ethers-io/ethers.js/tree/3ea4c226dd0b3a074abf90748de9d11192027f4f) |
| 173 | [wevm/viem](https://github.com/wevm/viem) | Conservada | [`2450e26872b4`](https://github.com/wevm/viem/tree/2450e26872b47aac7dc9f098298c04d2e8d4f374) |
| 174 | [ethereumjs/ethereumjs-monorepo](https://github.com/ethereumjs/ethereumjs-monorepo) | Conservada | [`11695f6cec3d`](https://github.com/ethereumjs/ethereumjs-monorepo/tree/11695f6cec3d99e143169e51ee91a0b6d146908f) |
| 175 | [paradigmxyz/reth](https://github.com/paradigmxyz/reth) | Conservada | [`53b5db1c3bc8`](https://github.com/paradigmxyz/reth/tree/53b5db1c3bc841bae679e58a625485d3d44d5b74) |
| 176 | [besu-eth/besu](https://github.com/besu-eth/besu) | Conservada | [`10dc5130f742`](https://github.com/besu-eth/besu/tree/10dc5130f7424488cc5730fca1e98565a313714b) |
| 177 | [ethereum/hive](https://github.com/ethereum/hive) | Conservada | [`befb5c9edf4e`](https://github.com/ethereum/hive/tree/befb5c9edf4e1df25351e2a4ebdaca15e3d5d01b) |
| 178 | [crytic/crytic-compile](https://github.com/crytic/crytic-compile) | Conservada | [`7e8a89ddd771`](https://github.com/crytic/crytic-compile/tree/7e8a89ddd7718d387b0c7b4e43a7391e1a6d79f3) |
| 179 | [smartbugs/smartbugs](https://github.com/smartbugs/smartbugs) | Nueva | [`a24600362277`](https://github.com/smartbugs/smartbugs/tree/a246003622775c730d5522429d8fed8846406e17) |
| 180 | [LiteSVM/litesvm](https://github.com/LiteSVM/litesvm) | Conservada | [`c848c5617d1a`](https://github.com/LiteSVM/litesvm/tree/c848c5617d1ae4d3f832fb0ca03e30c611a7ba52) |
| 181 | [anza-xyz/mollusk](https://github.com/anza-xyz/mollusk) | Conservada | [`81d1463aabad`](https://github.com/anza-xyz/mollusk/tree/81d1463aabad700c3bb953827215c5dfc81ca61a) |
| 182 | [otter-sec/anchor](https://github.com/otter-sec/anchor) | Conservada | [`98846e3bb753`](https://github.com/otter-sec/anchor/tree/98846e3bb753a2e5b701d58d2655f76c8f41a01e) |
| 183 | [anza-xyz/agave](https://github.com/anza-xyz/agave) | Conservada | [`07289a669228`](https://github.com/anza-xyz/agave/tree/07289a6692285a1f3bdb4a1121b24f0c5a589298) |
| 184 | [lfdt-ibc/ibc-go](https://github.com/lfdt-ibc/ibc-go) | Conservada | [`873b622380fb`](https://github.com/lfdt-ibc/ibc-go/tree/873b622380fbbce76ac407c6e0299fcbec557045) |
| 185 | [CosmWasm/cosmwasm](https://github.com/CosmWasm/cosmwasm) | Conservada | [`b7da6a4d373f`](https://github.com/CosmWasm/cosmwasm/tree/b7da6a4d373f5fdb7cd752f855271ed9909ec1ce) |
| 186 | [cosmos/cosmos-sdk](https://github.com/cosmos/cosmos-sdk) | Conservada | [`0c3dd0e3eb54`](https://github.com/cosmos/cosmos-sdk/tree/0c3dd0e3eb5413ea86fddaa9e8fbe8c16fda815b) |
| 187 | [MystenLabs/sui](https://github.com/MystenLabs/sui) | Conservada | [`f0f5a5f03da8`](https://github.com/MystenLabs/sui/tree/f0f5a5f03da8ae1a90c3858dafcfa460f851fcf4) |
| 188 | [starkware-libs/cairo](https://github.com/starkware-libs/cairo) | Conservada | [`4a078b123ce2`](https://github.com/starkware-libs/cairo/tree/4a078b123ce242b2a04c0eaae790a976a8da469a) |
| 189 | [ethereum/consensus-specs](https://github.com/ethereum/consensus-specs) | Conservada | [`2d519bc04f0f`](https://github.com/ethereum/consensus-specs/tree/2d519bc04f0f9c52f0e0876f69b238a9523f1ef8) |
| 190 | [ethereum/EIPs](https://github.com/ethereum/EIPs) | Conservada | [`b4b2ac745e77`](https://github.com/ethereum/EIPs/tree/b4b2ac745e77291d7b47d45665d4e016ab58d31e) |
| 191 | [crytic/building-secure-contracts](https://github.com/crytic/building-secure-contracts) | Nueva | [`0e679905ce33`](https://github.com/crytic/building-secure-contracts/tree/0e679905ce336d81b1eade9cfe924011e9073339) |
| 192 | [theredguild/damn-vulnerable-defi](https://github.com/theredguild/damn-vulnerable-defi) | Nueva | [`64fddf9f96de`](https://github.com/theredguild/damn-vulnerable-defi/tree/64fddf9f96de2782f8868898d68673acb295119c) |
| 193 | [OpenZeppelin/ethernaut](https://github.com/OpenZeppelin/ethernaut) | Nueva | [`d05643a40aa9`](https://github.com/OpenZeppelin/ethernaut/tree/d05643a40aa98c45d66247c69ffceab8f44dd8cb) |
| 194 | [juice-shop/juice-shop](https://github.com/juice-shop/juice-shop) | Nueva | [`c9f99228d9d5`](https://github.com/juice-shop/juice-shop/tree/c9f99228d9d56afb5f5ca7925376292f7fa44b13) |
| 195 | [WebGoat/WebGoat](https://github.com/WebGoat/WebGoat) | Nueva | [`4e98f1cbbf89`](https://github.com/WebGoat/WebGoat/tree/4e98f1cbbf896fdd06edcc9930515ebe0ade7c69) |
| 196 | [OWASP/crAPI](https://github.com/OWASP/crAPI) | Nueva | [`b5fc307f3e5f`](https://github.com/OWASP/crAPI/tree/b5fc307f3e5f875809b095b771108ef342a33724) |
| 197 | [digininja/DVWA](https://github.com/digininja/DVWA) | Nueva | [`502ac150ce37`](https://github.com/digininja/DVWA/tree/502ac150ce37c20ca6e04cab7c5ca959f315f2d0) |
| 198 | [vulhub/vulhub](https://github.com/vulhub/vulhub) | Nueva | [`9b90d4276f84`](https://github.com/vulhub/vulhub/tree/9b90d4276f84feed6333286afeb7e1250379a1da) |
| 199 | [OWASP/CheatSheetSeries](https://github.com/OWASP/CheatSheetSeries) | Conservada | [`c2a1e3e32cec`](https://github.com/OWASP/CheatSheetSeries/tree/c2a1e3e32cec12f27be0a3b1e771ce51288a363e) |
| 200 | [OWASP/mastg](https://github.com/OWASP/mastg) | Conservada | [`e8183038d7a8`](https://github.com/OWASP/mastg/tree/e8183038d7a88c1ac962732d6e3f6e7f40a0251c) |
