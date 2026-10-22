# H2D — auditoría posterior del enlace PFT

Fecha: 2026-10-22. Repositorio destino: `josuechavando350-png/nexus-quant-capital`,
ID `1411047452`. Cambio limitado a `omega/`; PR #30 sobre Census v3.

**H2 permanece en 93.75% (94% redondeado). Certificación: 0/36. Census abierto.**
Se completa el enlace local de fuente PFT y el build release pendiente. No se
cierra el cuarto control H2: todavía faltan forks y replay desconectado.

## Identidad que realmente se verificó

- Implementación publicada: `b1a093e11e92acb59c796e220786ff6346d2a1f9`.
- Árbol: `0efdbd44e673552bb5aef6895363cf1001ae0be2`.
- Padre: `bd033838814eb19d139996bc16da8dbd28ede415`.
- Lectura independiente de GitHub: repositorio ID, commit, árbol y padre
  coinciden; fetch y comparación local del árbol sin diferencias.
- Fuente original: `e259739c9f75fedcd1061d2f78d6b8852e7a3060`.
- Certificado PFT original: `5b4a0cb778cb4370cd54eb6fcba765dc8d7cecdf`.

`evidence/h2-pft-binding.json` es el recibo de esa ejecución exacta. El commit
posterior que contiene esta auditoría incorpora documentación, evidencias,
allowlist y una prueba adicional; no debe confundirse con el productor del
recibo. El adaptador no cambia entre ambos. No existe una nueva corrida CI,
workflow ni artifact de certificación: esos campos permanecen `null`.

## Resultados

| Comprobación | Resultado |
|---|---|
| Objetos y grafo original | PASS: `git fsck`, padres completos, ausencia de grafts/replacements/shallow |
| Materializador/perfil | Blobs originales fijados; no se altera `ROOT` ni se elimina la comprobación de ancestros |
| Enlace real con NQC | PASS en checkout limpio del commit publicado; recibo íntegro reproducido y árboles recalculados |
| Aislamiento | PASS: 637 payloads originales, 531 fuentes, 106 workflows desactivados, 0 activos |
| Pruebas nuevas del adaptador | 32/32; fixtures sintéticos claramente separados de evidencia original |
| Omega completo | 273/273; 0 errores, omisiones o expected failures; D15B/D16 auténticos |
| Rust Census 1.98.1 | 528/528; 0 fallos/ignoradas; workspace/all-targets, locked/offline |
| Rust PFT sobre copia recién vinculada | 56/56; check/all-targets y build release aprobados, locked/offline |
| Solidity sobre copia recién vinculada | Build con tamaños y 14/14 tests; Foundry 1.7.1, solc 0.8.24, seed `0x39`; dos fuzz de 256 casos |
| Formato PFT heredado | Conserva FAIL de H2C; es dato registrado por el contrato original, no un gate de build |
| Forks históricos | NO EJECUTADOS; se conserva preflight H2C HTTP 403 de ambos proveedores |
| Replay en namespace desconectado | NO EJECUTADO; se conserva bloqueo H2C `Operation not permitted` |

El build release se comprobó primero sobre la copia H2C y después sobre la copia
producida por el enlace publicado. El segundo es el resultado principal de H2D.
La regresión Python Census de H2C no se repitió: ningún archivo heredado cambió;
conserva sus siete errores de preparación y la ejecución histórica separada de
174 tests. No se presenta como discovery agregado verde.

## Pruebas de rechazo y correcciones encontradas

Las 32 pruebas cubren repositorio/ID sustituido, commit/tree incorrecto, objeto
Git corrupto bajo su nombre original, padre ausente, historia reemplazada o
truncada, source protegido modificado incluso con `assume-unchanged`, cambios de
modo, symlinks, recibo distinto, certificado reetiquetado, permisos promovidos,
árbol efectivo alterado, claves JSON duplicadas y salida solapada con entradas.

La primera ejecución real encontró un error de normalización de rutas con `..`:
se resolvieron después de comprobar symlinks y se añadieron dos regresiones. La
siguiente rechazó correctamente el checkout destino shallow; se recuperó su
historial completo por fetch de lectura. Ambas ejecuciones se repitieron y el
enlace pasó tanto localmente como en el commit publicado.

La auditoría añadió corrupción física de un objeto Git en un repositorio
sintético temporal. Su primer intento encontró el objeto de sólo lectura; el
fixture ahora cambia el modo de ese único objeto desechable antes de corromperlo.
La prueba confirma el rechazo por hash de objeto, no un error del fixture.
Ningún objeto original se corrompió ni se modificaron bytes protegidos.

## Formato y límites restantes

El workflow inerte `nqc-protocol-fork-source-binding.yml.disabled` explica que
el source recuperado es inmutable. Captura códigos de salida de fmt/lint con
`set +e`, después exige check/test/release con `set -e`. Por eso el tratamiento
correcto es mantener FAIL/advertencias visibles sin editar fuente histórica.
No se cambió ese contrato ni se reinterpretó fmt como PASS.

El adaptador verifica la identidad de contenido local. La lectura de GitHub se
conserva aparte; no se inyecta autoridad remota en el recibo offline. Falta un
productor CI nuevo con identidad exacta, evidencia de fork y replay conforme al
contrato, artefactos autenticados y validación posterior del consumidor para
hablar de recertificación. Triadas reales, cobertura y economía completa siguen
siendo requisitos de Census. No se otorgan permisos de firma, broadcast o gasto.

## Evidencia reproducible

`evidence/h2-pft-audit.json` enlaza SHA-256 de archivos y comandos; el registro
completo Omega está en `h2-pft-omega.json`. `h2-pft-logs.json` conserva los logs
de los gates ejecutados, cada uno con hash de su texto original. El recibo PFT
contiene los hashes de ambas copias efectivas y los overlays originales.
Para repetir el enlace, seguir `PFT_SOURCE_BINDING_CONTRACT.md` en un checkout
limpio, con fuente original separada y un directorio de salida nuevo.
