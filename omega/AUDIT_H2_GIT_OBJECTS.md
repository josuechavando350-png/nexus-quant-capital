# Auditoría H2B — aislamiento completo a nivel de objetos Git

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Estado

Esta auditoría complementa H2 sin ejecutar GitHub Actions ni tocar fondos. Reproduce
las condiciones estructurales de `migration/verify_isolation.py` sobre los árboles
Git completos del repositorio destino y del repositorio fuente.

**Head Omega auditado:** `84fbaa2dd7a1b93c432f6611622b98d81fd3c679`  
**Tree Omega auditado:** `449d6fcdf0e8ca839c73ae06a0ff462dc26c3d82`  
**Main base:** `16e352225ba8a6a931834c4edf3d86d9a2924b7d`

Esto NO es recertificación, NO cierra Census y NO sustituye la ejecución local
del verificador, Python, Rust, PFT/forks o EVM replay.

## Resultado del árbol destino

- Árbol completo: 812 entradas, 691 blobs.
- Omega: 46 blobs.
- Manifest importado: **637/637 rutas presentes**.
- Fuentes NQC: **531**.
- Workflows históricos: **106**, todos bajo
  `ci/migration/legacy-workflows/*.yml.disabled`.
- Workflows activos bajo `.github/workflows/`: **0**.
- Symlinks: **0**.
- Rutas prohibidas por el verificador
  (`.github/`, `.vercel/`, `apps/`, `packages/`, `runtime/`): **0**.
- Archivos raíz no revisados: **0**.
- Membresía importada: 637 esperados / 637 observados / 0 extra / 0 faltantes.
- Modos Git de los 637 payloads: **637/637 coinciden** con manifest.

## Identidad de payload

El manifest contiene 631 entradas `byte_identical` y 6 adaptaciones
`test_workflow_path_only`.

### 631 byte-identical

**631/631** blobs destino coinciden exactamente con `source_git_blob` del
manifest. No hubo mismatch de blob ni de modo.

### 6 adaptaciones permitidas

Cada fuente fue leída directamente de
`josuechavando350-png/nexus-engine` en el commit
`e259739c9f75fedcd1061d2f78d6b8852e7a3060`. Se aplicaron únicamente los
reemplazos declarados por el manifest y el resultado se comparó con el blob
destino.

Resultado: **6/6 transformaciones exactas**.

| Destino | Source blob | Destination blob |
|---|---|---|
| `ci/nqc-census/test_rmc006_recertification_runner.py` | `24b2db9dd83e51acaad5e35bab57bf2538699240` | `cf841d30f913c12afac60861bfb7d8c91569fa19` |
| `ci/nqc-census/test_rmc006_recertification_workflow.py` | `739e6fb0f4d90bbd50c837573e6343752f36c5ff` | `782c56d28153d37f069884821e829f5ebc8fc450` |
| `ci/nqc-census/test_rmc011_historical_source_compatibility.py` | `47f3ddca82f86f1e5791e7c4403e1d8dcf5ffd84` | `ae4b36cddcaf2513c49769553ca14c8e85653f4b` |
| `ci/nqc-census/test_rmc011_independent_discovery_admission.py` | `78d096699c7aca9dd48073ae50a52aa2391ea469` | `7e6af37510ba2d6205b44fedcae67b4a3ef9f127` |
| `ci/nqc-census/test_verify_rmc011_audit_workflow_contract.py` | `2c02ee957fa143f0509cc33769d0d9dea1b39ac9` | `1897b846814a1167d1707712cb4cdf4175e8c9ae` |
| `ci/nqc-census/test_verify_rmc011_bounded_family_promotion.py` | `cbbcfa913c7d5fdf5a49df9d07d3725ea38d4cf3` | `0707f3079f1c65dcda6801dc0bd843b10289cbf2` |

## Árbol fuente independiente

Fuente: `josuechavando350-png/nexus-engine`.

- Commit fuente manifestado:
  `e259739c9f75fedcd1061d2f78d6b8852e7a3060`.
- Tree manifestado:
  `c9cc97b31daa96c3c427c6781333a706e988f342`.
- Tree leído directamente del commit fuente:
  `c9cc97b31daa96c3c427c6781333a706e988f342`.
- Las **637/637** rutas fuente existen en ese árbol.
- **637/637 source Git blobs** coinciden con el manifest.
- **637/637 modos** coinciden.
- Missing: 0. Blob mismatch: 0. Mode mismatch: 0.

## Referencias históricas inmutables

Se leyeron directamente los diez commits fuente listados por
`original_refs`. Resultado: **10/10 tree SHA coinciden exactamente**:

- protocol_fork_certified
- rmc001_merge
- rmc002_merge
- rmc004_base
- rmc003_typed_authority
- rmc003_2_authority
- d06_base
- d06_original_source
- recertification_base
- pr668_import_source

## Aislamiento de los cambios Omega

Comparación de `main` `16e352225ba8a6a931834c4edf3d86d9a2924b7d`
contra el head auditado:

- 82 commits ahead, 0 behind.
- 46 archivos modificados/agregados.
- **46/46 están bajo `omega/`**.
- Cambios fuera de `omega/`: **0**.

Por tanto, proyectando fuera la allowlist Omega, los bytes Git preexistentes
permanecen iguales al main importado.

## Qué prueba y qué NO prueba

Esta auditoría sí demuestra, a nivel de objetos Git y reglas estructurales, que:

- la identidad fuente/destino del manifest no cambió;
- la membresía importada es exacta;
- los blobs y modos fuente son los declarados;
- las seis transformaciones son exactamente las autorizadas;
- no hay workflow activo, symlink ni árbol cliente/deploy prohibido;
- Omega no alteró ningún archivo preexistente fuera de su directorio;
- las diez referencias históricas siguen ligadas a sus trees originales.

No equivale a ejecutar físicamente:

`python3 migration/verify_isolation.py --source-git <object-store-original>`

porque en este entorno no existe un checkout/almacén Git local completo. Tampoco
recalcula mediante ese proceso local todos los SHA-256 ni ejecuta las suites
Python/Rust/PFT.

## Avance H2

H2 tenía cuatro controles principales. Los tres primeros estaban cerrados. Del
cuarto — aislamiento + regresión completa — queda cerrada ahora la mitad de
identidad/aislamiento estático sobre árboles Git completos; la mitad ejecutable
sigue pendiente.

**H2 = 88%** (87.5% redondeado).  
**Omega certificado = 0/36. Census = NO CERRADO.**

Pendiente para H2 100%:

1. Ejecutar el verificador original sobre checkout completo y object store fuente.
2. Ejecutar regresión Python completa y clasificar los errores/skips históricos.
3. Ejecutar Rust `cargo test --workspace --all-targets --locked --offline`,
   fmt/Clippy/build según el contrato importado.
4. Ejecutar las comprobaciones PFT/fork/replay que requieren el entorno físico.

No se habilitarán workflows ni se conectarán fondos para cerrar estas pruebas.
