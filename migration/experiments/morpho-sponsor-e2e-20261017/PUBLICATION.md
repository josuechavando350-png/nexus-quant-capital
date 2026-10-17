# Publicación y procedencia

Repositorio: `josuechavando350-png/nexus-quant-capital`. Rama exclusiva: `research/nqc-morpho-sponsor-e2e-20261017`. Base: `544fd2d16d0b1cf1018dce006702a7abcbf0d0c6`.

| Commit remoto ya verificado | Contenido | Árbol idéntico al local probado |
|---|---|---|
| `bac646aabd6b272c774fa67345422626ef0c5d0a` | Lock y selección determinista de 12 tx; no filtro de beneficio | `b532e9e11c5e9b2917e47a0a31f3165cc9b8881f` |
| `9188d693255fc4ebc03c4499b046f651ba8b4e8d` | Primer ciclo, 21 escenarios, 90 recibos, ledger y tests | `62f1063dd36050c457a82096743e457ef74fe48c` |

El commit que contiene este documento añade el expediente y **corrige la configuración del optimizador Morpho** para igualar el bytecode de la referencia anterior. Su HEAD se identifica mediante el propio commit contenedor en GitHub o `git rev-parse HEAD`; no se escribe dentro del archivo un hash autorreferencial. Los resultados anteriores permanecen en `9188d693...`; los vigentes se reproducen con el código y evidencia de este árbol. `evidence/optimizer-alignment.json` conserva el cambio exacto.

La publicación usa objetos Git con comparación de tree SHA antes de mover la rama; no merge ni force-push. La identidad de autor/committer del conector puede dar un commit SHA distinto del commit local, por lo que se exige igualdad del árbol completo. Tras fetch se alinea el HEAD local únicamente cuando esa igualdad está probada; los archivos no se sustituyen.

`evidence/reference-readback.json` conserva las cuatro referencias protegidas NQC y Engine solo lectura. Engine ya estaba en `32f2cec34bff23279e4952dc85bfc228754ccc96` al comienzo del estudio: su diferencia con el SHA del PDF procede de trabajo ajeno, no de este proyecto. No se modificó Engine, main, la rama Morpho ni las dos auditorías. No se activó ningún workflow.

`MANIFEST.sha256` cubre todos los archivos publicados de este directorio excepto el propio manifiesto. Verificación desde este directorio: `sha256sum -c MANIFEST.sha256`. Los archivos de `build/` son productos regenerables ignorados por Git. Los datos históricos se referencian en su ubicación original, sin copiarlos ni alterarlos para conseguir paridad.
