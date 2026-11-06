# Continuidad para la siguiente sesión / Claude

## Misión y límites vigentes

Integrar NQC y DIABLO dentro del repositorio `nexus-quant-capital`. Preservar
fuentes e identidades históricas, trabajar con código ejecutable y evidencia,
no prometer plataforma perfecta ni ganancias. Mantener los 27 requisitos de
integración y las 50 capacidades sin marcar módulos amplios por pruebas de
subcomponentes. No modificar nexus-engine, Cano, Vercel, secretos ni workflows.

## Estado comprobado

Esta entrega concilia localmente PR35 (adc28a06), PR37 (42dc168e) y los parches
locales de privacidad/regresiones. El punto de aplicación único es el commit
adc28a062668de996848ace5d233d2fa055fbd4c, no main ni una rama posterior al azar.
Todos los IDs de tests previos están en `reconciliation-origins.json`.
La evidencia actual está en `reconciliation-validation.json` y en el paquete
adjunto de validación, no en los recibos históricos heredados.

El conector GitHub expuesto en esta sesión tuvo acciones de lectura, no de
creación de commits. El entorno no tenía `gh` y Git no resolvió github.com.
No se publicaron commits, no se fusionaron PRs y no se cambió main. No confundir
un parche probado localmente con una rama remota actualizada.

## Cómo retomar sin volver a empezar

Leer README y CONSOLIDATION; verificar la cabeza remota antes de aplicar nada.
En un checkout limpio y en una rama de trabajo del commit base, comprobar
el manifiesto de blobs previos y `git apply --check`. Aplicar el parche sin
force push; ejecutar `review-platform`, `verify-platform`, `review` y
`verify-review`. Publicar solo código/documentación, nunca evidencia sensible.
Si cambió la cabeza remota, reconciliar primero; no sobrescribirla.

Los contadores de los 27 puntos se generan desde integration-checklist.json;
la vista integration_milestones.json debe coincidir. capabilities.json conserva
los 50 requisitos. La integración heredada de Candidate/Reconstruction recibe
evidencia externa y no confirma explotación. RMC-016 es un solver de capacidad,
no un reconstructor universal de contratos.

## Pendientes materiales no realizados

Publicación remota de esta conciliación; suite/aislamiento históricos de NQC;
pruebas EVM de propiedades de código propio; reconstrucción verificable de
estado e impacto; benchmark ciego de detección; evaluación de reglas de bounty,
clasificación final y operación multiprograma. No hay hallazgos reales ni pagos.
Las funciones de evasión, robo de credenciales y explotación autónoma de terceros
no están implementadas; mantener alternativas defensivas y revisión humana.

No agregar otro módulo antes de confirmar que la versión conciliada está
publicada o identificar expresamente la base local desde la que se continúa.

## Continuación: política local de permisos

La base LOCAL es el paquete de 380 pruebas, conservando sus comparaciones de
regresión. También se incorporaron los 18 tests exclusivos y controles de la
variante de 342 y la exportación minimizada con 41 tests de la variante de 328.
El nuevo módulo `permissions.py` añade 48 tests de políticas RBAC declaradas.
Ningún test de esas tres entradas se elimina. La base remota de aplicación sigue
siendo adc28a062668de996848ace5d233d2fa055fbd4c; no confundir esta base con un
commit que contenga los cambios locales.

Hay un solo árbol consolidado. `project_context.py` comparte el inventario de
pruebas entre los modos de reporte; `publication/` es obligatorio en el reporte
conjunto. `sharing.py` usa el formato de exportación v2 para conservar PARTIAL.
Los puntos 14 y 24 avanzan a PARTIAL únicamente por la revisión del modelo JSON.
No hay extracción de políticas desde aplicaciones, búsqueda de escaladas,
PoCs contra terceros ni cambios de permisos en producción.

Mantener la procedencia y hashes de las tres entradas en el manifiesto de la
entrega. Repetir QA y revisar la cabeza remota antes de publicar. Este trabajo
no habilita workflows ni despliegues. Ver PERMISSIONS.md y el recibo actual.

Validación ejecutada de la continuación: 487 pruebas aprobadas en el flujo
conjunto y en una copia limpia parcheada; 439 IDs anteriores conservados y
48 nuevos. Cinco casos numéricos fijos, 256 generados y dos políticas JSON
calibradas. No publicación remota. Digest de fuentes: 33b23d569ca292e60f05c9afade8bf88acee0e9ab41fcad3f9c83ea51d0025df.

## Continuación: 25 iniciativas + resultados estáticos (04 noviembre 2026)

Partir del paquete local de permisos de 487 pruebas, no de una versión parcial
anterior. Se agregan static_review.py y research_plan.py, registro JSON de las
25 iniciativas de ambos PDF y sus pruebas. Se mantienen las 487 pruebas previas.
Los puntos amplios de SlithIR/detectores no se marcan completos por leer JSON.
El avance de TRAIL_OF_BITS.R1 es parcial: transporte de resultados estáticos
con localización, hashes y deduplicación; no análisis de Solidity ejecutado.

Los docs se leyeron completos, con imágenes de sus seis páginas. Se conservaron
IDs de las 25 iniciativas y hashes de los dos PDF. El dictamen del Informe 02
es desarrollo modular local, no certificación. Sus referencias comerciales no
se adoptan como métricas propias. No hay copia de código propietario.

No se instaló Slither/solc: no estaban disponibles y DNS externo falló. Nunca
fabricar una salida de herramienta real; los ejemplos y tests declaran
synthetic-format-fixture. Las salidas originales se guardan privadas.

El repositorio remoto se consultó con el conector: PR35 todavía en adc28a06,
sin fusión. En esta sesión no se publicaron cambios. No confundir los manifiestos
locales con commits remotos. Ver recibo de validación actualizado del paquete.

## Continuación: dominio finito de permisos (04 noviembre 2026)

Base local explícita: SUPERHUNTER_estatico_553.zip, no la rama remota reducida del
importador. Se reejecutaron sus 553 tests antes de cambiar el código. Se agregaron
permission_domain.py y sus tests, con las mismas políticas declaradas del motor
permissions.py. El objetivo de conectar Slither/solc sigue bloqueado: no hay
instalación y las solicitudes HTTPS a PyPI/solc fallaron por DNS. No se presentan
salidas sintéticas como ejecución de esos binarios.

Nuevo verificador: enumeración de configuraciones, no explorador de ataques ni
motor SMT. Presupuestos incompletos devuelven INCONCLUSIVE, no PASS. Referencias
de permisos y enumeración deben coincidir. Las propiedades y el dominio son
suministrados; no se infieren desde Solidity ni se demuestra alcanzabilidad real.
#24 y #34 son parciales; CERTORA.R1 avanza parcialmente. Todos los requisitos
previos siguen presentes. Consultar el registro de validación de esta entrega
para los resultados realmente ejecutados, no los recibos históricos heredados.


## Continuación: conciliación de balances (04 noviembre 2026)

Base: paquete local SUPERHUNTER_dominios_permisos_591.zip (no volver a una rama
remota reducida). Se reejecutaron las 591 pruebas sin fallos/errores/omisiones.
Un intento previo interrumpido por timeout del entorno se conserva como incompleto.
La instalación de Slither/solc sigue ausente y curl a PyPI volvió a fallar DNS.
No se fabricaron outputs de analizador, contratos o ejecuciones EVM.

balance_reconciliation.py añade conciliación de balances/movimientos suministrados
con aritmética entera y Decimal independiente, cotizaciones opcionales declaradas,
estados de cobertura e integridad de evidencia. La etapa economics es obligatoria
en review-platform/verify-platform. El laboratorio corre tres controles sintéticos:
correcto, diferencia de una unidad mínima e información incompleta.

Los 27 hitos y 25 iniciativas no se marcan completos por esto. El punto 37 de las
50 capacidades solo es PARTIAL en aritmética, no triaje ni impacto de vulnerabilidades.
Los nombres de tests anteriores se conservan; las expectativas de conteos se
actualizan por el componente añadido, sin retirar pruebas negativas.

No hay publicación remota en esta continuación. El parche es incremental contra
la entrega local 591; no aplicarlo directamente sobre adc28a06/895e1c2e o main.
El ZIP contiene el árbol completo acumulativo y manifiestos de antes/después.
La siguiente sesión debe leer el recibo final de validación que acompaña el ZIP,
no tomar los contadores históricos de este documento como resultado del HEAD.
