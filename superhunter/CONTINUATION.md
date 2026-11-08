# SuperHunter — punto de reanudación del 7 de noviembre de 2026

## Mapa recuperado

El código acumulativo de partida es PR #83, rama
`fix/superhunter-visible-dependency-index-20261107`, commit
`93b5a34fca1159dcfb6b3e41631003612c0604f9`. La rama main mantiene el estado de
continuidad por separado; no sustituye a esta rama de código. El respaldo
`SUPERHUNTER_INDICE_DEPENDENCIAS_CERRADO_20261107.zip` contiene evidencia, no todo
el código. Sus 338 entradas declaradas en MANIFEST se comprobaron sin diferencias.

Lectura rectora: `../AGENTS.md`, `../SUPERHUNTER_MASTER_PLAN.md` y el
`SUPERHUNTER_STATUS.md` vigente de main, junto con los PR y sus cabezas actuales.
Los documentos HANDOFF anteriores conservan historia; sus números no prevalecen
sobre una ejecución posterior identificada.

| Registro | Cantidad | Estado del registro recuperado |
| --- | ---: | --- |
| `integration-checklist.json` | 27 | 12 implementados con límites, 3 parciales, 12 pendientes |
| `capabilities.json` | 50 | 9 parciales, 24 planeados, 17 requieren rediseño |
| `research_initiatives.json` | 25 | 5 parciales, 20 planeadas |
| `repo_portfolio_50.json` | 50 | Candidatos catalogados; las aceptaciones de laboratorio posteriores tienen documentación separada |
| `../SUPERHUNTER_MASTER_PLAN.md` | 100 SH-* | Propuestas adicionales; no sumarlas como avance implementado |

Se mantienen M0–M5, los requisitos de evidencia y el objetivo de operación
continua. Los conteos de tests y catálogos no constituyen porcentaje de capacidad.
NQC Defense es un trabajo separado.

## Incremento de esta continuación

Se implementa el siguiente paso explícito del estado posterior a #83:
[informe de cobertura temporal](OWNED_AUTHORITY_COVERAGE.md), con algoritmo
incremental, referencia de historial, CLI y verificador. El corpus y las métricas
históricas permanecen intactos. El caso `latent_revocation` sigue siendo una
omisión histórica, aunque su hueco de entradas ahora se describe expresamente.

## Validación de esta continuación

- Baseline #83 reproducido: **2,654/2,654 PASS**, cero fallos/errores/skips;
  verificador separado PASS sobre el digest histórico.
- Incremento: **2,676/2,676 PASS**, cero fallos/errores/skips; `verify-check`
  separado PASS. Digest `b7eb0d8c628c2a0304a4d7e9fa602631d74eb4ba246d446f4b42d4ba0fd77ee9`.
- 22 pruebas nuevas; 2,654 identidades anteriores preservadas en sus mismos
  ocho grupos. Presupuestos históricos intactos.
- Informe temporal generado y verificado por la CLI en procesos separados.
  Once casos, nueve secuencias distintas; ocho condiciones, una ausente de todo
  el corpus. La ausencia de revocación de latent_revocation permanece visible.
- Límite de repositorio PASS; 642 archivos históricos intactos. Verificador
  original y nueve tests PASS en copia exclusivamente histórica. Rust no
  reejecutado; no hay nueva certificación PFT/Census.
- Slither, Geth/EELS y perfil de SDK OpenTelemetry real no reejecutados sobre
  este digest; sus aceptaciones históricas no se trasladan a esta entrega.

Se detectó que el Python predeterminado 3.12.14 de este entorno no expone las
constantes fcntl de sellado. El primer pase completo con ese runtime registró un fallo y cuatro errores;
queda conservado como diagnóstico fallido; no se cambian código ni pins para forzarlo a pasar. Se preparó Python
3.12.3 con PyYAML 6.0.3 y cryptography 46.0.4; la biblioteca nativa Z3 existente
coincide con el SHA fijado `7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`.

No se instala un nuevo scanner ni se ejecutan herramientas contra terceros.
Las aceptaciones Slither/Geth/EELS de #83 siguen perteneciendo a su digest
histórico hasta una repetición nativa explícita sobre un nuevo digest.

## Próximo trabajo verificable

Repetir las aceptaciones nativas existentes sobre el nuevo digest, conservando
resultados y denominadores separados. Revisar si hace falta ampliar las
condiciones de cobertura de laboratorio en un corpus nuevo y versionado, sin
reescribir los once casos ni borrar la omisión histórica. Las nuevas condiciones
deben tener definición, contra-controles y comparación con una referencia.

La plataforma sigue incompleta; avance global no determinado, ninguna
vulnerabilidad original confirmada ni operación 24/7 en 20 programas acreditada.
