> **Conciliación más reciente de Slither:** [SLITHER_TRIPLE_REPLAY.md](SLITHER_TRIPLE_REPLAY.md) unifica el gate de tres controles y la comparación de dos expedientes completos con hashes externos. Todavía no hay scanner real ejecutado ni QA global certificado en esta rama.

---

> **Último incremento de Slither:** [SLITHER_THREE_CONTROL_GATE.md](SLITHER_THREE_CONTROL_GATE.md) añade un segundo negativo adversarial basado en la regla upstream: `tx.origin == msg.sender`. El QA debe contrastar tres reportes privados y rechazar todos los fallos. Slither y solc reales todavía no se ejecutaron en este entorno.

---

> **Nuevo control de Slither (laboratorio):** [SLITHER_PAIR_GATE.md](SLITHER_PAIR_GATE.md) exige reporte positivo y control limpio sin alertas, coherencia de fuente/commit y dos expedientes privados. No se ha ejecutado Slither real ni QA completo en esta rama; no equivale a integración certificada.

---

> **Segundo adaptador (Slither #6, no certificado):** [SLITHER_OWNED_LAB.md](SLITHER_OWNED_LAB.md) describe el runner local sobre Solidity propio y fijo, con compilador y fuente comprobados por hash, supervisión del proceso y reutilización de import-slither. Slither no está instalado en GitHub/usuario y no se ha ejecutado la suite completa en esta rama. No habilitar targets externos.

---

> **Primera integración en laboratorio (sin Collector):** [OTEL_QA_LAB.md](OTEL_QA_LAB.md) describe la instrumentación local de QA con OpenTelemetry SDK, su instalación opcional, resultados de pruebas y criterios aún pendientes. No hay exportación OTLP ni hallazgos externos; no se considera una integración verificada de producción.

---

> **Nuevo punto de entrada para otras IAs — 50 repositorios externos (2026-11-07):** consultar [REPOSITORIES_50.md](REPOSITORIES_50.md) y [repo_portfolio_50.json](repo_portfolio_50.json) antes de planear dependencias, junto con [plan maestro](../SUPERHUNTER_MASTER_PLAN.md) y [estado](../SUPERHUNTER_STATUS.md). Catálogo documental, no ejecución o integración de terceros. Los apartados históricos siguientes conservan su alcance.

---

# Continuación vigente: comparación nativa de configuraciones

La nueva ruta `review-compiler-variants` exige una aceptación nativa aprobada de
esta misma versión y compara el comportamiento observado de los tres controles
propios con código directo sin optimizar, directo optimizado y vía IR optimizado.
`replay-compiler-variants` vuelve a compilar y ejecutar. Son configuraciones del
mismo solc sobre la misma EVM, no dos implementaciones independientes.

Ver [COMPILER_VARIANTS.md](COMPILER_VARIANTS.md) y
[HANDOFF_COMPILER_VARIANTS.md](HANDOFF_COMPILER_VARIANTS.md). Los resultados reales
de la entrega están en VALIDATION.json y los registros fuera del árbol de código.
Los apartados siguientes se conservan como historia de sus perfiles.

---

# Continuación vigente: EVM local con estado y reversiones

La ruta `run-evm-state-controls` compila y ejecuta tres controles aritméticos
propios en la EVM nativa verificada de Geth. `replay-evm-state-controls` repite
la compilación y ejecución desde las fuentes fijas. Comprueba inicialización,
persistencia, precondiciones, Panic(0x01), reversión y agotamiento de gas.

Ver [EVM_STATE_CONTROLS.md](EVM_STATE_CONTROLS.md) y
[HANDOFF_EVM_STATE.md](HANDOFF_EVM_STATE.md). La aceptación nativa es una ejecución
separada del gate de tests; ni sus cifras ni las de los documentos históricos
certifican capacidades de descubrimiento. Los apartados siguientes son registros
anteriores: las menciones de EVM pendiente corresponden a sus propias entregas.

No se admiten objetivos, contratos externos, RPC o transacciones por esta ruta.
La entrega es local; no afirma publicación ni fusión con GitHub.

---

# Continuación: inventario de declaraciones desde fuente (perfil v4)

> Entrega local posterior: 1,422 pruebas del paquete y aceptación nativa de controles Solidity/Z3. Los registros anteriores describen entregas históricas; no acreditan ejecución EVM. Véase SOLIDITY_FORMAL_CONTROLS.md.


La revisión `review-compiler-layout` admite ahora un manifiesto externo v4.
Contrasta el inventario de variables de estado obtenido leyendo toda la fuente,
no solamente las declaraciones que afirman el AST y el layout. Ver
[SOURCE_DECLARATION_INVENTORY.md](SOURCE_DECLARATION_INVENTORY.md).

Esta ampliación NO ejecuta solc ni una EVM; limita lo que puede concluirse cuando
el AST aportado omite declaraciones. Los informes anteriores se conservan como
historia, no como la validación vigente. Los resultados de esta entrega se
registran en VALIDATION.json, fuera del árbol de código del paquete.

---

# Continuación actual: expediente con orden contable obligatorio

## Nueva revisión de correspondencia fuente–AST–layout

`review-compiler-layout` y `verify-compiler-layout` contrastan las entradas y
salidas Standard JSON suministradas con un manifiesto externo. Comprueban el
contrato seleccionado, la cobertura de declaraciones, sus posiciones en bytes y
el layout mediante el comparador existente. No ejecutan ni autentican una
compilación. Ver [COMPILER_LAYOUT_BINDING.md](COMPILER_LAYOUT_BINDING.md).


La base local recuperada es `SUPERHUNTER_secuencia_contable_1019.zip`.
`review-case` y `verify-case` soportan el perfil v2: cuatro paquetes de evidencia,
identidad externa de libro/orden y rechazo de secuencias contradictorias aunque
los saldos finales cuadren. El perfil v1 conserva compatibilidad, pero declara
expresamente que no comprobó orden. Ningún perfil confirma vulnerabilidades.

Consulte [ORDERED_CASE.md](ORDERED_CASE.md) y
[HANDOFF_ORDERED_CASE.md](HANDOFF_ORDERED_CASE.md). Los resultados exactos de esta
entrega están en el recibo de validación adjunto al ZIP, no en los contadores
históricos que siguen. Los catálogos 27/50/25 no se modifican.

---

# Entrega actual: registro multiprograma offline

## Incremento local: orden de movimientos contables

La entrega de secuencia contable amplía la conciliación final con precondiciones
de saldo y límites uint256 por movimiento. Se integra como etapa obligatoria
`sequence/` de `review-platform`; no ejecuta contratos ni EVM. Consulte
[LEDGER_SEQUENCE.md](LEDGER_SEQUENCE.md) y
[HANDOFF_LEDGER_SEQUENCE.md](HANDOFF_LEDGER_SEQUENCE.md) para el perfil,
reproducción, procedencia y límites. Los registros anteriores se conservan como
historia; los resultados de esta entrega van en su manifiesto de validación.


## Incremento: expediente de revisión cruzada

`review-case` / `verify-case` enlazan Candidate, alcance declarado, diagnósticos
estáticos y balances. Cada módulo se vuelve a verificar y después se exige
coincidencia de repositorio/commit/cadena/bloque y referencias externas.
Los resultados siguen siendo revisión o inconcluso, nunca hallazgo confirmado.
Ver `CASE_REVIEW.md` y `HANDOFF_CASE_REVIEW.md` para interfaces y límites.


Esta entrega consolida contabilidad, Z3 y enlaces de código e incorpora
Program Intelligence. Registro local para ocho etiquetas de plataformas;
**cero conectores activos y cero autorizaciones de programas reales verificadas**.
El código acumulativo pasó 769 pruebas en seis grupos disjuntos; la variante
publicada focalizada pasó 380. No confundir esos árboles ni sus identidades.
Ver [HANDOFF_MULTIPLATFORM.md](HANDOFF_MULTIPLATFORM.md) y
[PROGRAM_INTELLIGENCE.md](PROGRAM_INTELLIGENCE.md). Los textos siguientes son
registros anteriores; no sustituyen el estado y límites de esta entrega.

---

# Estado de la continuación actual: conciliación económica

Se continúa desde el paquete local de 591 pruebas sin descartar la consolidación
anterior. El módulo nuevo, sus comandos y la etapa obligatoria `economics/` se
explican en [ACCOUNTING.md](ACCOUNTING.md). Los resultados de ejecución están en
`validacion/` del ZIP de esta entrega; los números más abajo son registros históricos.
La implementación sigue siendo local y no confirma vulnerabilidades de terceros.

El modelo permite contrastar los balances con sus movimientos, detectar hasta
una unidad mínima de diferencia y distinguir cobertura incompleta. Cotizaciones
no suministradas permanecen desconocidas. No hay cálculo de fondos robables.

Los 27 requisitos se conservan en 12 implementaciones delimitadas, 3 parciales
 y 12 pendientes. Los 50 IDs conservan 9 parciales, 24 pendientes y 17 por reformular;
las 25 iniciativas, 4 parciales y 21 pendientes. Ningún módulo amplio está completo.
No usar estas cuentas como porcentaje de avance funcional.

---

# SUPERHUNTER — revisión defensiva local integrada

Base remota de aplicación: `adc28a062668de996848ace5d233d2fa055fbd4c`.
Los cambios de este paquete son **locales y no publicados**. No se presupone
que los PR 35 y 37 estén fusionados. Ver `HANDOFF.md`.

Se conservan las funciones de las entregas de 380, 342 y 328 pruebas: ambos
reportes, privacidad, exportación minimizada y comparador de regresiones.
El nuevo módulo de políticas de permisos añade funcionalidad defensiva a los
puntos 14 y 24. No es un Hunter autónomo ni confirma vulnerabilidades reales.

## Políticas de permisos

```bash
python3 -m superhunter audit-permissions --policy /ruta/privada/policy.json --out /tmp/sh-policy-001
python3 -m superhunter verify-permissions --bundle /tmp/sh-policy-001
```

Analiza una política JSON de roles declarada por el operador: herencia,
denegación explícita, usuarios deshabilitados, separación por permisos y
escenarios de revocación. Dos algoritmos independientes deben coincidir.
Los eventos se registran con AuditLog nativo de DIABLO. El verificador recalcula
resultados, grafo, reporte y referencias de evidencia. Ver `PERMISSIONS.md`.

Un resultado PASS significa únicamente que las propiedades declaradas se
cumplen en el modelo. No demuestra que un contrato o aplicación lo aplique.
No se realizan peticiones, cambios de roles ni intentos de acceso.

## Recorrido conjunto del paquete

Linux/POSIX, Python 3.11+ y PyYAML para las fuentes nativas. No hay instalaciones,
servicios o workflows activados automáticamente.

```bash
python3 -m superhunter review-platform --out /tmp/sh-review-001
python3 -m superhunter verify-platform --bundle /tmp/sh-review-001
```

Ejecuta las pruebas del paquete, cinco casos numéricos nativos DIABLO/NQC y 256
casos de fuzzing numérico. Verifica el inventario completo, las referencias y
los 27+50 requisitos. El componente de permisos forma parte del QA y su reporte.
Este comando no afirma haber comprobado ninguna política de producción.

La carpeta `review/` contiene las vistas consolidadas y `publication/` contiene
el reporte portátil autocontenido. Su presencia y verificación son obligatorias.
**Ambas contienen datos privados**: el filtrado de textos no elimina los
originales ni garantiza encontrar todos los secretos. El veredicto global
mantiene `platform_complete=false` y `vulnerability_confirmed=false`.

## Exportación minimizada y regresiones

```bash
python3 -m superhunter share-review --review /tmp/sh-review-001/publication --out /tmp/sh-shared-001
python3 -m superhunter verify-shared --bundle /tmp/sh-shared-001 --review /tmp/sh-review-001/publication
```

La exportación no copia los logs ni artefactos originales. Conserva los hitos
parciales con el esquema v2; sigue requiriendo revisión humana. Ver `SHARING.md`.
`compare-checks` y `verify-comparison` mantienen sus controles de eliminación o
modificación de pruebas y asociación a identidades de código. Ver `REGRESSION.md`.

Se conservan `export-diablo`, `import-nqc`, `review`, `verify-review`, `local-lab`,
`verify-lab`, `fuzz-lab`, `verify-fuzz` y la interfaz legacy. El puente de evidencia
sigue en REVIEW_REQUIRED; no se lo presenta como ejecución verificada de PoCs.

## Contexto y validación

`integration-checklist.json` es el registro rector de los 27 puntos;
`integration_milestones.json` es una proyección que debe coincidir. El inventario
estático de tests es compartido por los dos reportes mediante `project_context`.
`capabilities.json` conserva los 50 IDs.

Los 27 hitos mantienen 12 implementaciones acotadas, 3 parciales y 12 pendientes.
Las 50 capacidades tienen 7 parciales (3, 14, 24, 29, 45, 47, 48), 26 pendientes,
17 por reformular y ninguna completa. No convertirlos en porcentaje de capacidad.

```bash
python3 -m unittest discover -s superhunter/tests -v
python3 -m superhunter check --out /tmp/sh-qa-001
python3 -m superhunter verify-check --bundle /tmp/sh-qa-001
```

Esta versión contiene 487 tests distintos: 439 IDs preservados de las tres
entregas y 48 de permisos. Sus resultados ejecutados constan en
`permissions-validation.json`; los registros anteriores son históricos.

No se ejecutaron contratos EVM, Forge, forks, RPC, explotación, transacciones,
envío de reportes ni GitHub Actions. La suite histórica completa NQC y su
verificador de aislamiento no están incluidos en este checkout parcial.
No se heredan certificaciones. Los hashes no autentican productores remotos.

## Continuación desde los dos resúmenes

Se incorpora un importador offline de resultados Slither y un registro trazable
de las 25 iniciativas adicionales. Ver STATIC_REVIEW.md. No se ejecutó Slither
ni solc; el importador usa fixtures etiquetados y no acredita detección real.

```bash
python3 -m superhunter initiatives
python3 -m superhunter import-slither --report REPORTE --context CONTEXTO --sources FUENTES --out NUEVO_DIRECTORIO_PRIVADO
python3 -m superhunter verify-slither --bundle DIRECTORIO_PRIVADO
```

Las cifras de validación de secciones anteriores son históricas. El recibo de
esta continuación se entrega en validacion/VALIDATION.json del paquete adjunto.
La base LOCAL es SUPERHUNTER_permisos_integrados_487.zip; la base remota de
aplicación acumulativa sigue identificada por adc28a062668de996848ace5d233d2fa055fbd4c.

## Verificación de dominios finitos de permisos

`check-permission-domain` y `verify-permission-domain` enumeran configuraciones
RBAC declaradas, comprueban invariantes y revocaciones y distinguen cobertura
completa de presupuesto agotado. Ver [PERMISSION_DOMAIN.md](PERMISSION_DOMAIN.md).
No es SMT, análisis de Solidity ni prueba de explotación.

## Custodia firmada de evidencia (incremento local)

`seal-evidence` y `verify-custody` incorporan firmas Ed25519 con confianza externa
por expediente/productor, caducidad y revocación. Reutilizan bundles existentes,
AuditLog nativo y el gate de QA. No convierten una firma en prueba de ejecución o
vulnerabilidad. Ver CUSTODY.md y HANDOFF_CUSTODY.md. Dependencia opcional de este
componente: requirements-custody.txt; fue probada con cryptography 46.0.4.


## Medición por caso y control RBAC conocido

Se añaden `evaluate-benchmark`, `verify-benchmark`, `benchmark-permissions` y
`verify-permission-benchmark`. La revisión conjunta exige la etapa
`benchmark_control/`. Precisión, recall global y condicional, cobertura,
abstenciones y errores se mantienen separados. Una muestra omitida bloquea
la evaluación; un porcentaje sin denominador queda indefinido. Las variantes
con hashes/grupos compartidos entre splits se rechazan según el manifiesto.

Estos controles NO miden la detección general del Hunter ni prueban un benchmark
ciego. Ver BENCHMARK.md y HANDOFF_BENCHMARK.md. Los registros de tests anteriores
siguen siendo históricos; no implican ejecución de esa misma versión hoy.

## Reparación de admisión nativa

La dependencia `DIABLO.ScopeGuard.rate_limiter()` está incorporada y fijada por
hash. El laboratorio numérico utiliza admisión no bloqueante antes del cálculo
NQC y conserva cinco fuentes nativas. Ver [NATIVE_RATE_REPAIR.md](NATIVE_RATE_REPAIR.md).
Los conteos de las secciones anteriores son registros históricos, no una medida
de completitud de esta versión.

## Revisión de compatibilidad de almacenamiento

`review-layout` y `verify-layout` comparan artefactos de layout suministrados,
con referencias externas y auditoría DIABLO. El control de calidad ejecuta sus
pruebas junto a las anteriores. No ejecutan solc ni aprueban upgrades; los
renombrados, gaps y formatos fuera de perfil requieren revisión. Consulte
[STORAGE_LAYOUT.md](STORAGE_LAYOUT.md) y [HANDOFF_STORAGE_LAYOUT.md](HANDOFF_STORAGE_LAYOUT.md).


## Controles formales nativos de Solidity (incremento local)

La ruta `prove-solidity-controls` conecta solc fijado, consultas SMT, Z3 real,
diagnósticos del compilador y referencia exhaustiva de tres controles propios.
No es ejecución EVM ni análisis de objetivos externos. La aceptación nativa
requiere el binario y se ejecuta aparte del gate unitario. Véase
[SOLIDITY_FORMAL_CONTROLS.md](SOLIDITY_FORMAL_CONTROLS.md) y
[HANDOFF_SOLIDITY_FORMAL.md](HANDOFF_SOLIDITY_FORMAL.md).

## Control nativo con estado persistente

`prove-stateful-controls` y `replay-stateful-controls` conectan solc CHC, Z3,
referencias finitas y AuditLog para tres fuentes propias fijas. Distinguen un
incumplimiento en la tercera operación, una propiedad conservada, vacuidad y
presupuesto inconcluso. No ejecutan una EVM ni aceptan objetivos arbitrarios.
Perfil y comandos: [SOLIDITY_STATEFUL_CONTROLS.md](SOLIDITY_STATEFUL_CONTROLS.md).

## Revisión conjunta con aceptación nativa obligatoria

`review-native-platform` ejecuta el recorrido local completo y añade la ejecución
EVM, conciliación de efectos persistentes y un replay nativo obligatorio antes
de generar el informe conjunto. `verify-native-platform` exige una huella de
fuentes externa y vuelve a ejecutar los controles nativos. Ver
[NATIVE_PLATFORM_REVIEW.md](NATIVE_PLATFORM_REVIEW.md).

El `review-platform` anterior conserva su alcance; pasar ese comando solo no
acredita el nuevo perfil nativo. No se ejecutan objetivos externos ni se confirman
hallazgos por aprobar controles propios.

## Comparación de configuraciones de compilación

La ruta adicional `review-compiler-variants` consume la aceptación nativa de la
misma versión y contrasta dos perfiles optimizados con el perfil original.
El replay vuelve a ejecutar las herramientas. Ver [COMPILER_VARIANTS.md](COMPILER_VARIANTS.md).
No equivale a usar otro compilador/EVM ni completa las capacidades amplias.
