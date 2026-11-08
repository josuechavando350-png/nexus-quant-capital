# SuperHunter — punto de reanudación del 7 de noviembre de 2026

## Estado vigente

La cabeza ejecutable aceptada es PR #84, commit
`09d8826643cee9c1c9cea06c125303625523540c`, rama
`feat/superhunter-owned-temporal-coverage-20261107`. Se completó la repetición
nativa pendiente sobre su digest, sin cambiar código, fixtures ni dependencias
fijadas. El detalle, límites y evidencia están en
[NATIVE_REACCEPTANCE_PR84.md](NATIVE_REACCEPTANCE_PR84.md).

- QA con SDK OpenTelemetry real: **2,676 PASS**, cero fallos, errores o skips;
  verificación del expediente en otro proceso sin SDK instalado.
- Slither nativo y replay separado: un positivo y dos negativos esperados.
- Geth/EELS: cuotas con cuatro positivos y dos negativos correctos; autoridad
  temporal con seis positivos, cuatro negativos correctos y **una omisión**,
  `latent_revocation`. Los denominadores permanecen separados.

La aceptación de laboratorio no acredita capacidades generales, hallazgos
originales, integración en producción de los 50 repositorios ni operación 24/7.
El avance global sigue sin un porcentaje validado. Los apartados siguientes
conservan la recuperación y validación inicial de #84; sus pendientes nativos
quedan atendidos por la aceptación identificada arriba.

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

## Validación inicial de #84 (registro histórico)

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
- En el cierre inicial de #84, Slither, Geth/EELS y perfil de SDK OpenTelemetry
  real no se habían reejecutado sobre este digest. La repetición posterior
  consta en el estado vigente; no es un traslado de resultados de #83.

Se detectó que el Python predeterminado 3.12.14 de este entorno no expone las
constantes fcntl de sellado. El primer pase completo con ese runtime registró un fallo y cuatro errores;
queda conservado como diagnóstico fallido; no se cambian código ni pins para forzarlo a pasar. Se preparó Python
3.12.3 con PyYAML 6.0.3 y cryptography 46.0.4; la biblioteca nativa Z3 existente
coincide con el SHA fijado `7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`.

En la entrega inicial no se instaló un nuevo scanner ni se ejecutaron
herramientas contra terceros. Las aceptaciones de #83 mantienen su identidad
histórica; la repetición posterior de #84 tiene expedientes separados.

## Próximo trabajo verificable

Revisar las condiciones ausentes del informe de cobertura temporal y definir
un corpus adicional de laboratorio propio, con versión y denominadores
separados. Debe conservar los once casos históricos, sus entradas y etiquetas,
la omisión `latent_revocation` y los resultados anteriores. Cada condición nueva
necesita definición, contra-controles y contraste con la referencia. Antes de
implementar una ampliación, distinguir cobertura de entradas de detección de
defectos: observar más entradas no demuestra por sí mismo una detección mejor.

La plataforma sigue incompleta; avance global no determinado, ninguna
vulnerabilidad original confirmada ni operación 24/7 en 20 programas acreditada.
