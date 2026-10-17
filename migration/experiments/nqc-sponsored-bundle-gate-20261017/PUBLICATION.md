# Publicación verificada

Rama autorizada para Directiva 004: `research/nqc-sponsored-bundle-gate-20261017`, creada desde `937a833a481fd69d2ce96152deb7d4d0760d6596` tras comprobar que no existía.

| Commit publicado | Contenido | Tree Git comprobado |
|---|---|---|
| `3005efa548fd8a3af4e9ef49af4c0fa9608fac6b` | Arnés, compilación, conciliación, criterio económico y pruebas | `4514f2a670f5f835f77c1e478eeb685bac0cad80` |
| `6003febb2ee1639a0a80efef6d87839e6e6cf833` | Recibos/trazas, resultados, negativos, comandos, continuidad y manifest | `95dc545e2b4553829ccf2aabdff8301ad1b1ebfa` |

Ambos commits se publicaron mediante el conector GitHub autorizado; se leyó la referencia, se hizo fetch y se comprobó diff vacío entre el árbol publicado y el local. Los hashes de commits locales anteriores al conector difieren por metadatos de autor/fecha; sus trees son idénticos. No se usó force-push ni se modificó main. Un dry-run de push CLI encontró ausencia de credenciales; no se solicitó ni extrajo ninguna, y la publicación se completó con el conector existente.

El commit que agrega este sello contiene solo publicación/manifiesto/continuidad: su identidad se obtiene con `git log -1 --format=%H -- migration/experiments/nqc-sponsored-bundle-gate-20261017/PUBLICATION.md`. No se incrusta un hash autorreferencial en el archivo. El HEAD final se comprueba con `git rev-parse HEAD` y contra la referencia remota.

Read-back de los cuatro refs protegidos: main `16e352225ba8a6a931834c4edf3d86d9a2924b7d`; 003 `937a833a481fd69d2ce96152deb7d4d0760d6596`; 001 `544fd2d16d0b1cf1018dce006702a7abcbf0d0c6`; revisión independiente 002 `5e4d5814b9063b342e10a6d828c3c480f85c097f`. Se mantienen sin cambios. `evidence/github-readback.json` conserva el resultado de lectura del commit de evidencia.

Toda diferencia frente a 937a833 está dentro de la carpeta 004. Los 67 archivos anteriores de Directiva 003 se compararon byte por byte con esa base. SHA-256 del conjunto nuevo: MANIFEST.sha256 (excluye el propio manifiesto). Los artefactos build/out-upstream/cache son regenerables e ignorados; sus fuentes, compiladores y hashes sí están fijados. No se publican claves, firmas ni credenciales.
