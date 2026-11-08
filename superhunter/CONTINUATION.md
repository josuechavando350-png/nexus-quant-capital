# SuperHunter — punto de reanudación del 8 de noviembre de 2026

## Estado vigente: contraste del diagnóstico con el cómputo restringido

Sucesor de PR #106, commit `cf7784d48cae79982fa177357bca51af24b7da19`.
[OWNED_RESTRICTED_CORROBORATION.md](OWNED_RESTRICTED_CORROBORATION.md) describe
el consumidor que revalida ambos expedientes y enlaza los cinco pares de
ensayos con los dos findings y planes ya existentes. No inicia procesos,
no ejecuta planes y no crea findings adicionales.

- **3,242 QA PASS**, cero fallos/errores/skips. Se conservan las 3,227 pruebas
  anteriores en sus grupos; 15 nuevas al grupo 2. Focales: 15 PASS.
- Digest `2f7a662741657c214c9152214dd03d4ec8416dfc2d7225c77106de7d9799bf53`.
  SDK real y verificador separado sin SDK PASS. Máximo worker 91.687612 s;
  grupo 2: 76.394039 s. Presupuestos históricos intactos.
- Los diez ensayos reales de los tests enlazan inventario, delta, retorno,
  evidencia del filtro y hashes de los findings y planes. Los baselines exigen
  igualdad de bytes; los fallos conservan las etiquetas distintas de cada perfil
  y admiten solo el motivo y estados cerrados esperados.
- Una primera versión asumió etiquetas iguales y falló en dos tests con un error
  adicional. El intento está conservado. La corrección mantiene las identidades
  originales y añade rechazo de una etiqueta arbitraria con el mismo motivo.
- Descriptor adicional real, diagnóstico truncado declarado, evidencia alterada
  y resellada, IDs repetidos y mutación durante lectura no producen corroboración
  completa. El consumidor no convierte un inconcluso en hallazgo confirmado.
- 265 de 268 Python anteriores idénticos; solo cambian entrada y dos registros
  de QA. Ningún test previo reescrito; 642 históricos intactos y mismo rechazo
  legado `unreviewed root file`, sin recertificación de NQC.

Los intervalos son observaciones declaradas, sin autenticación del reloj ni
independencia causal. El filtro sigue limitado al cálculo de datos ya cargados.
M1 permanece parcial. No hay nuevas corridas nativas EVM/Slither ni hallazgos
externos confirmados. Los ensayos sostenidos de esta sesión mantienen fuentes
congeladas PR105 y PR106: su resultado no se transfiere a este digest. La corrida
inicial interrumpida conserva su estado incompleto, sin resultado final y con
sus residuos documentados. Las aceptaciones posteriores sobre la fuente
publicada se guardan con su propio expediente; no se anticipa su resultado aquí.

Los siguientes apartados conservan los resultados y fuentes anteriores.

## Estado vigente: cálculo propio restringido y evaluación de QA indexada

Sucesor de PR #105, commit `f3c244097a8883398b7ebe5899b77687e4031f56`.
[OWNED_RESTRICTED_REVIEW.md](OWNED_RESTRICTED_REVIEW.md) describe el nuevo
perfil de cinco ensayos sobre una copia propia. La adquisición doble ocurre
antes del filtro; la política de integridad se calcula después, sobre bytes
en memoria. No admite comandos ni objetivos arbitrarios.

- **3,227 QA PASS**, cero fallos/errores/skips. Se conservan las 3,192 pruebas
  anteriores y sus grupos; 35 nuevas al grupo 0. Focales: 86 PASS.
- Digest `f2cf2c7f681d4c75b881701d9f92a2686fa11fe0aca084d968bfba24003daa2f`.
  SDK real y verificador separado sin SDK PASS; límites históricos intactos. Máximo worker
  93.293218 s; grupos 5 y 7: 87.360798 s y 78.945046 s.
- Controles nativos de apertura, directorio, sockets, memoria y descriptores;
  disponibilidad previa de sockets explícita. Una instalación fallida o salida
  inesperada conserva INCONCLUSIVE y detiene los ensayos sin cálculo alternativo.
- Corrección de admisión: registrar la identidad del descriptor efectivamente
  abierto evita la fuga cuando la ruta cambia entre stat y open. Cuatro
  regresiones nuevas de IO real; no se borra la ruta reemplazada.
- QA asigna filas por un índice local a cada llamada. Mantiene coincidencias de
  prefijos, orden, duplicados, propietarios compartidos y todos los gates. Cinco
  regresiones comparan la referencia directa. La comparación sintética de 12
  pares caracteriza esa función; no representa ejecución real de los tests del
  fixture ni rendimiento general de la plataforma.
- Se conservan dos corridas integrales bloqueadas por CPU y una redistribución
  experimental no publicada. La versión final conserva los grupos originales;
  ningún límite se aumentó y ningún test anterior fue reescrito.
- 256 de 261 Python anteriores idénticos; cambian entrada, boundary, workspace
  y dos registros de QA. 642 archivos históricos intactos; mismo rechazo legado
  `unreviewed root file`, sin recertificación de NQC.

El filtrado delimita el cómputo propio, no el acceso previo a archivos, la
integridad de memoria, otro proceso del mismo UID ni un sandbox general.
M1 sigue parcial. No se crean findings de seguridad, no se ejecutan reparaciones
externas y no hay nuevas corridas nativas EVM/Slither. Los expedientes de captura
y diagnóstico anteriores conservan sus perfiles e identidades originales.

## Estado vigente: limpieza comprobada de temporales propios

Sucesor de PR #104, commit `4af508c34caf78dd8fd6ee718b95e1c9e3a1a6c1`.
[OWNED_WORKSPACE.md](OWNED_WORKSPACE.md) documenta el ciclo de vida integrado
en captura y diagnóstico. Ambos comprueban identidad, limpieza y ausencia
antes de publicar el expediente. No se barren residuos históricos.

- **3,192 QA PASS**, cero fallos/errores/skips. Las 3,166 identidades anteriores
  conservan sus grupos; se añaden 26 regresiones al grupo 0. Focales: 26 PASS.
- SDK real y verificador separado sin SDK PASS. Máximo worker 98.671674 s;
  grupo 0: 70.750861 s. Presupuestos históricos sin cambios.
- Digest `70a4bdee043fab12d4c800acf8812b38d909f94ab4840d4e59c3718d718a017b`.
- 255 de 259 Python anteriores idénticos. Cambian captura, diagnóstico y dos
  registros; ningún test previo reescrito. 642 históricos intactos y mismo
  rechazo legado `unreviewed root file`; no hay recertificación de NQC.
- El candidato inicial de 3,190 PASS tuvo después un control real que expuso
  una fuga de descriptor al perder el FD raíz. Se conserva ese fallo. El cierre
  corregido intenta liberar todos los FD todavía propios y rechaza pérdida de
  identidad; no cierra un descriptor observado reasignado a otro objeto.
- La ausencia observada no garantiza ausencia futura ni aislamiento del host.
  El ensayo sostenido nuevo mantiene fuente congelada, recibos y tiempos propios;
  no convierte la corrida histórica con residuos en una limpieza correcta.

M1 sigue parcial. No hay nuevo hallazgo externo, operación 24/7 acreditada,
ejecuciones nativas EVM/Slither nuevas ni cambios en los estados de catálogo.
Los siguientes apartados conservan resultados y digests históricos.

## Estado vigente: findings operativos y plan de corrección

Sucesor de PR #103, commit `bee9a64668bf3cc8561893c62e8967c74effd7e3`.
[OWNED_REMEDIATION.md](OWNED_REMEDIATION.md) describe la integración directa
en el diagnóstico existente: perfil/schema v2, dos findings operativos y sus
planes derivados solo de los cinco ensayos completos. Un inconcluso conserva
cero findings y cero acciones. No se ejecutan reparaciones propuestas.

- **3,166 QA PASS**, cero fallos/errores/skips; 3,148 IDs anteriores conservan
  sus grupos y se añaden 18 al grupo 0. 42 focales PASS (24 previas +18 nuevas).
- SDK real y verificación separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 96.911316 s; grupo nuevo 63.572750 s; límites intactos.
- Digest `d81e15e6a520f3804836683181ea88fccf94cbaba8180bf6730644f0d5855896`.
- Cada finding enlaza baseline, fallo y restauración con hashes, deltas,
  modo, retorno y tiempos. El plan exige revisión de una copia propia nueva,
  referencia verificable, delta vigente e inventario completo restaurado.
- No se infiere aprobación humana, estado actual, severidad de seguridad,
  incidente ni vulnerabilidad. El fallo de modo conserva la referencia de
  contenido; el código de error compartido no identifica por sí solo la causa.
- La aceptación adicional conserva cinco ensayos reales, verificación CLI,
  controles de manipulación y timeouts por SIGSTOP explícito en workers propios.
  Los detalles, cantidades y recibos quedan en el expediente de aceptación;
  un timeout no se convierte en éxito ni se presenta como caída natural.
- 255 de 258 Python anteriores idénticos. Cambian el diagnóstico y dos
  registros; ningún test previo se reescribe. No hay nuevas corridas EVM/Slither.
- Los expedientes v1 no se migran en silencio: requieren su código y checkout
  originales para revisión semántica; su conservación de bytes sigue disponible.
- 642 históricos intactos; mismo rechazo legado unreviewed root file en
  PR103 y aquí. No se recertifica NQC.

Evidencia: `SUPERHUNTER_DIAGNOSTICO_Y_PLAN_CORRECCION_20261108.zip`.
M1 sigue parcial y 1/6 hitos cerrados. La prueba mínima de Bubblewrap falló
en este entorno antes del payload; no se acredita aislamiento del SO.
La prueba sostenida conserva PR100 congelado y tiene su expediente separado.
El siguiente cierre requiere aceptación integral de M1 con aislamiento
efectivo y su evidencia delimitada, sin confundir estos dos controles propios
con investigación general o hallazgos de terceros.
Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: verificación conjunta de archivos y custodia

Sucesor de PR #102, commit `1291a4fa165b68e25d4a615264b2a135bed6d604`.
[PRESERVED_CUSTODY.md](PRESERVED_CUSTODY.md) documenta la comprobación conjunta
del índice, todos sus ZIP y una firma Ed25519 con política externa fijada.
Un índice con conteos falsos se rechaza aunque su firma sea válida.

- **3,148 QA PASS**, cero fallos/errores/skips; las 3,129 anteriores conservan
  sus ocho grupos y se añaden 19 al grupo 0. Las 19 focales también pasaron.
- SDK real y verificación separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 97.574358 s; grupo nuevo 48.252565 s; límites intactos.
- Digest `4ee28c1cb2173b096b1b42e5e53896273d68560fe44b8cd711dcbea4fd052644`.
- 21 controles CLI sobre bytes conservados en PR101. Colección mixta:
  11 entradas, 10 ZIP, 5 inventarios y 8 capturas incompletas; retorno 1.
  Colección completa: 3 entradas, 2 ZIP, 1 inventario; retorno 0.
- Ocho anclas/identidades incorrectas, caso/productor equivocados, revocación,
  expiración, firma corrupta, archivos ausentes/alterados y promociones de
  garantías se rechazan. Firma válida sobre índice falso también se rechaza.
- Clave de laboratorio efímera en memoria; ninguna privada persistida.
  Misma máquina: no custodia independiente, identidad humana, ejecución
  autenticada ni reloj confiable. Sellar capturas incompletas no las completa.
- 253 de 256 Python anteriores idénticos; solo cambian tres registros.
  Ningún test anterior reescrito ni nuevas ejecuciones nativas.
- 642 históricos intactos; mismo rechazo legado por unreviewed root file
  en PR102 y aquí. No se recertifica NQC.

Evidencia: `SUPERHUNTER_CUSTODIA_INDICE_VERIFICABLE_20261108.zip`.
M1 parcial y 1/6 hitos cerrados. La prueba sostenida mantiene la versión
congelada de PR100; sus resultados se documentan por separado al terminar.
Siguiente: verificar íntegramente sus recibos y contrastar los pendientes
de M1 con los criterios del plan, sin convertir conservación en cierre del hito.
Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: verificación eficiente de aliases

Sucesor de PR #101, commit `28e0d3145e769fcfe7ccae88c263082a1aab0422`.
[INDEX_CACHE.md](INDEX_CACHE.md) documenta la reutilización de validaciones
del mismo ZIP y contexto dentro de una llamada. Cada alias conserva su lectura,
hash, identidad, presupuesto y comprobación final. No hay caché persistente.

- **3,129 QA PASS**, cero fallos/errores/skips; 3,121 anteriores conservadas
  en sus ocho grupos, ocho nuevas. 72 focales PASS (8 nuevas +34 índice +30 conservación).
- SDK real y revisión separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 98.907586 s; grupo nuevo 45.258801 s; límites intactos.
- Digest `547353d03eaae284d66215e48f6df020bff468de5ec448266aaa95409011b8f8`.
- Tres pares alternados por corpus, 12 procesos de medición reales. Medianas:
  64 aliases: construcción 4.981023→0.267334 s, verificación 5.078716→0.194029 s
  (18.63 y26.18 veces en esta muestra). 64 ZIP distintos: construcción
  5.087222→5.058754 s, verificación 5.201839→5.103855 s, tiempos similares.
- Los 64 ZIP distintos contienen variantes explícitamente sintéticas de
  identidad sobre un inventario propio; no representan 64 productores reales.
  Mismo Python3.12.3, host compartido con validación sostenida, tres pares:
  no garantía de rendimiento general ni afirmación de significancia estadística.
- Conteos idénticos, fixtures intactos; recibos y medianas recalculados en otro
  verificador. Seis controles CLI confirman lectura de índice PR100 y reporte
  de conservación PR101 con sus identidades históricas y rechazos correctos.
- 252 de 255 Python anteriores idénticos; cambian preserved_index.py y dos
  registros. Ningún test anterior reescrito, sin nuevas ejecuciones nativas.
- 642 históricos intactos y mismo rechazo legado unreviewed root file
  en PR101 y aquí. No se recertifica NQC.

Evidencia: `SUPERHUNTER_INDICE_DUPLICADOS_RENDIMIENTO_20261108.zip`.
M1 parcial, 1/6 hitos cerrados. La medición sostenida de PR100 continúa
y no se cuenta como resultado terminado de este incremento.
Siguiente: unir la custodia firmada del índice con la verificación de los
archivos para que una firma válida no apruebe un índice semánticamente incorrecto.
Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: política verificable de conservación

Sucesor de PR #100, commit `39f88c3f72319c265d405656a777738ad39ef73e`.
[PRESERVED_RETENTION.md](PRESERVED_RETENTION.md) documenta review-preserved-retention
y verify-preserved-retention: política externa exacta, índice y ZIP revalidados,
retenciones explícitas, mínimo de copias y presupuesto. Solo aliases exactos
son revisables; ningún resultado autoriza borrar o presume respaldos independientes.

- **3,121 QA PASS**, cero fallos/errores/skips; 3,091 anteriores en sus mismos
  ocho grupos, 30 nuevas asignadas al grupo 4. 30 focales finales PASS.
- SDK real y revisión separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 95.634890 s; grupo nuevo 47.737974 s. Presupuestos intactos.
- Digest `e7a91e7a14498996f814e7fa6af2aec53f5a712a4c6903dcdc94cf816b3ab60a`.
- 20 controles CLI sobre índice/archivos exactos de PR100: conservar 10 ZIP
  distintos y revisar un alias; exigir ambos aliases conserva 11 entradas.
  Mínimo dos copias informa 9 faltantes. Presupuesto de un byte incumple
  sin sacrificar las 10 entradas requeridas. Conteos/promociones recalculados
  y siete anclas/identidades incorrectas se rechazan.
- Ningún archivo histórico de evidencia se alteró o eliminó. El helper retira
  deliberadamente solo su nuevo archivo de política para probar su copia guardada.
  No se usan fechas ZIP ni se infiere ahorro físico, independencia o autenticidad.
- Lector actual, productor del índice y productor del reporte se fijan
  separadamente mediante digests externos. No se ejecutan productores antiguos.
- 250 de 253 Python anteriores idénticos; solo cambian tres registros.
  Ningún test anterior reescrito ni nueva ejecución nativa Geth/Slither/EELS.
- 642 históricos intactos; el aislamiento legado mantiene unreviewed root file
  tanto en PR100 como aquí. No se recertifica NQC.

Evidencia: `SUPERHUNTER_POLITICA_CONSERVACION_VERIFICABLE_20261108.zip`.
M1 parcial, 1/6 hitos cerrados. La medición sostenida de PR100 sigue en curso
y tendrá resultados propios; no se acredita aquí operación continua.
Siguiente: reducir verificaciones redundantes de aliases sin omitir hashes,
identidades ni anclas de cada entrada, con comparación de rendimiento acotada.
Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: índice privado de archivos y duplicados

Sucesor de PR #99, commit `f03f9afa9f7150cd873b1b1453e17970ad6a48ea`.
[PRESERVED_INDEX.md](PRESERVED_INDEX.md) documenta dos CLI reales para construir
y verificar colecciones explícitas, acotadas y privadas. No descubre archivos
ni ejecuta su contenido. Revalida cada ZIP y conserva anclas de productores anteriores.

- **3,091 QA PASS**, cero fallos/errores/skips; 3,057 anteriores conservadas
  en los mismos ocho grupos, 34 nuevas. Las 34 focales también pasaron.
- SDK real y revisión separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 92.585940 s; grupo nuevo 74.154944 s; presupuestos intactos.
- Digest `797724371c067b3688dad7357fdb4a0320ac9ec8d00fc37cc79c15c6a35a958a`.
- 17 controles CLI reales sobre datos de PR99: 11 entradas, 10 ZIP distintos,
  5 inventarios originales, 2 archivos con captura completa y 8 incompleta.
  Un alias no se cuenta como experimento independiente. Fuentes exactas conservadas.
- Control máximo de 64 aliases: un archivo/inventario único; 65 registros rechazados.
  Construcción 4.941977 s y verificación 5.133647 s en este host/corpus,
  no benchmark de archivos máximos ni garantía de rendimiento general.
- Manifiesto externo SHA256, esquema cerrado, salida privada nueva y dos pasadas
  de integridad/identidad. Índices previos requieren index_source_digest externo,
  separado del lector actual. Anclas de archivo y de inventario no prueban
  independencia, autenticidad, ejecución ni hallazgos.
- 248 de 251 Python anteriores idénticos; solo cambian tres registros.
  Ningún test anterior reescrito; ninguna nueva ejecución nativa Geth/Slither/EELS.
- 642 históricos intactos; el aislamiento legado conserva el mismo rechazo
  unreviewed root file en PR99 y aquí. No se recertifica NQC.

Evidencia: `SUPERHUNTER_INDICE_ARCHIVOS_VERIFICADOS_20261108.zip`.
M1 sigue parcial y 1/6 hitos globales cerrados. Siguiente: política explícita
de conservación de copias; no inferir antigüedad ni autorizar purgas por los ZIP.
Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: exportación privada con identidades preservadas

Sucesor de PR #98, commit `55358b980eb75fa30d6692c42f7056b57879af6a`.
[PORTABLE_COPY.md](PORTABLE_COPY.md) documenta export-preserved-copy y
verify-preserved-archive: salida nueva 0600, bytes privados sin cifrar/filtrar,
con elección explícita. Se verifica sin extraer ni ejecutar contenido.

`--source-digest` fija el lector actual y `--preserved-source-digest` fija, cuando
se indica, la identidad guardada en el expediente anterior. Reporte, anclas y
bytes históricos no se reescriben. El código antiguo no se ejecuta ni autentica;
se rederiva bajo el único perfil conocido. Sin segundo digest, ambos deben coincidir.
También se permite una salida hermana del checkout protegiendo la ruta del archivo;
se siguen rechazando rutas dentro del repositorio y symlinks.

- **3,057 QA PASS**, cero fallos/errores/skips. Las 3,017 anteriores siguen
  en sus ocho grupos; 40 nuevas. 101 focales finales PASS.
- SDK real y revisión separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 91.753291 s; grupo nuevo 58.518759 s. Presupuestos intactos.
- Digest `b1a08d189ce9879214f39e5c8b18f5c4bc157842279cb85c40b759f9e4bdf2fb`.
- 48 controles CLI con cinco workers propios (cuatro SIGKILL instrumentados y
  control limpio). Tras preservar/exportar se eliminan deliberadamente cinco
  carpetas originales y cinco de salvamento del helper. Veredicto idéntico.
- Otros 31 controles CLI cotejan cinco copias reales de PR98 con su respaldo
  previo fijado por SHA256 y conservan sus identidades/bytes. Se retiran solo
  clones temporales. Total final: 79 checks CLI. No es pérdida natural ni apagón.
- Se conservan la primera QA de 3,050 tests y los rechazos que reprodujeron el
  problema de identidad y de ruta de salida. La aceptación final usa los bytes nuevos.
- ZIP_STORED canónico, directorio acotado antes de asignación, anclas externas,
  inventario cerrado y contenido rederivado. Rechaza alteraciones/promociones,
  compresión, duplicados, rutas extra y truncado. Fechas ZIP fijas en 1980:
  no son evidencia temporal ni autorizan retención por antigüedad.
- 245 Python anteriores idénticos; tres registros y núcleo puro factorizado.
  Ningún test anterior reescrito. Escritor, motor y fixtures nativos intactos;
  no nuevas corridas nativas. Sin publicación de datos, purga o restauración.
- 642 históricos intactos. El aislamiento legado conserva unreviewed root file
  en PR98 y aquí. No se marca aprobado ni recertifica NQC.

Evidencia: `SUPERHUNTER_EXPORTACION_PRIVADA_VERIFICABLE_20261108.zip`.
Incluye expedientes actuales, controles alterados, prueba sobre los datos anteriores,
recibos, streams, comparación de IDs y helpers reproducibles.

M1 sigue parcial, 1/6 hitos globales cerrados. No acredita nuevos hallazgos,
autenticación independiente ni tres horas continuas. Siguiente: índice privado
con anclas externas y política explícita de retención; no usar fechas fijas del ZIP
para inferir antigüedad o borrar evidencia.

Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: copia verificable sin acceso al original

Sucesor de PR #97, commit `c654c53825c172028ad506b1ead92f5088c32e0c`.
[PRESERVED_COPY.md](PRESERVED_COPY.md) documenta la nueva ruta
`verify-preserved-copy`. Comprueba los bytes guardados y las anclas externas
sin abrir, buscar ni restaurar la carpeta original. No afirma su estado actual.
El verificador anterior que requiere el original conserva su comportamiento.

- **3,017 QA PASS**, cero fallos/errores/skips; 2,992 anteriores retenidas en
  sus mismos ocho grupos y 25 nuevas. 61 focales PASS.
- SDK real, revisión separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 90.909938 s; grupo nuevo 47.321798 s. Límites intactos.
- Digest `324a5e56ef87d801455b64aa3de8ab11ef2e41e0c6f5118bb09932758ebe40a4`.
- 36 checks CLI con cinco workers reales: cuatro cortes SIGKILL propios y
  un control limpio. Tras salvar los bytes, se retiran deliberadamente las
  cinco carpetas originales. Copia antes/después produce el mismo resultado;
  revisión con original rechaza su ausencia. No son pérdidas naturales de datos.
- El CLI conserva 1 para copias de originales incompletos y 2 para rechazo.
  Ni manifiesto recalculado ni reporte promovido evitan el cotejo con anclas.
  Integridad de bytes no equivale a autenticidad, semántica o ejecución probada.
- 244 Python anteriores idénticos; cambian los tres registros y se añaden
  módulo/tests. No se reescribe ningún test anterior. Escritor, motor y fixtures
  de PR97 permanecen intactos; no hay otra corrida nativa en este incremento.
- 642 históricos intactos. El aislamiento legado sigue rechazando la raíz
  ampliada tanto en PR97 como aquí; no se presenta como aprobado ni recertifica NQC.

Evidencia: `SUPERHUNTER_COPIA_VERIFICABLE_SIN_ORIGINAL_20261108.zip`.
Incluye cinco capturas reales, inventarios anteriores a la eliminación controlada,
paquetes conservados, controles alterados, comandos/recibos y helpers.
El ZIP PR97 conserva el bloque previo de escritura y su ejecución/replay Geth.

M1 sigue parcial y 1/6 hitos globales cerrados. No se acredita operación continua
de tres horas, autenticación independiente, restauración automática ni hallazgos.
Siguiente trabajo pendiente: política explícita de retención y exportación de
estos expedientes, manteniendo las anclas separadas y estados incompletos visibles.

Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: escritura interrumpida y salvamento verificable

Sucesor de PR #96, commit `db1bdf457690cb21f8ce107bcc466b2d7c64eabe`.
[BUNDLE_RECOVERY.md](BUNDLE_RECOVERY.md) explica el defecto reproducido, el
escritor corregido, la CLI de inspección/salvamento/verificación y sus límites.
Una entrada inválida deja de crear la carpeta y bloquear un reintento válido.
El marcador se publica desde un pendiente sincronizado, sin sobrescribir.

Cuatro cortes SIGKILL del propio proceso y un control normal ejecutan el escritor
real. El mismo corte sobre el escritor PR96 deja COMPLETE truncado; el nuevo
conserva esos bytes bajo el nombre pendiente. Un corte después del enlace se
clasifica como limpieza pendiente. No se simula apagón ni se certifica durabilidad.

El salvamento conserva cada byte en un expediente nuevo sin cambiar el original;
verifica anclas, inventarios, contenido y fuentes. Los originales incompletos
siguen con CLI 1 incluso después de salvarlos. El verificador actual requiere
que la carpeta original siga disponible; no reconstruye archivos nunca escritos.

- **2,992 QA PASS**, cero fallos/errores/skips; 2,956 anteriores retenidas en
  los mismos ocho grupos y 36 nuevas. 119 focales iniciales y ampliación de 195
  pruebas focales con salida 0. SDK productor real y verificación separada sin SDK.
- Máximo worker 89.427131 s; grupo nuevo 44.141788 s. Presupuestos anteriores intactos.
- Digest `0bc31fea59e9b1c26448b5c369c3df8b02df919a6ee20214c5b08e3775ee30e9`.
- 22 checks CLI con seis procesos de escritura reales: cuatro interrupciones
  nuevas, una del escritor antiguo y un control limpio. También hay controles
  de evidencia alterada, identificados como tales, sin promoción a éxito.
- 237 archivos Python anteriores idénticos; cambian escritor, tres registros
  y dos rutas de fixture en tests. Se conserva íntegra la captura antigua.
- La primera QA falló por ese fixture desactualizado: 1 fallo, 22 errores y
  40 tests no ejecutados. Los recibos fallidos se conservan, sin presentarlos como PASS.
- Se reejecutaron compilador/Geth fijados: tres controles enteros propios,
  3 constructores y 18 llamadas; replay real en otro proceso coincidió.
  La nueva captura es byte a byte la de esa ejecución. No es un hallazgo.
- El primer wrapper nativo impuso por error 2 GiB y bloqueó el límite original
  de 4 GiB del worker. Se corrigió el wrapper, sin modificar ese worker.
- Frontera complementaria: 642 históricos intactos. El verificador legado
  conserva `unreviewed root file` tanto en PR96 como ahora; no se recertifica NQC.

Evidencia: `SUPERHUNTER_RECUPERACION_ESCRITURA_20261108.zip`, con resultados
finales, aceptación real, errores iniciales, captura nativa y helpers reproducibles.
No se revalidan otros perfiles Geth, Slither o EELS. M1 continúa parcial: 1/6
hitos cerrados, sin operación continua acreditada ni explotación de terceros.

Siguiente: verificar el salvamento con sus anclas externas aunque ya no esté
disponible la carpeta original, sin convertir integridad de bytes en autenticidad.

Los apartados siguientes conservan sus estados y digests históricos.

## Estado vigente: diagnóstico de fallos y restauraciones propias

Sucesor de PR #95, commit `b2933041fdc7ad7c0c67254c475a82c59bad78a8`.
[OWNED_BOUNDARY_DIAGNOSIS.md](OWNED_BOUNDARY_DIAGNOSIS.md) documenta cinco
ensayos sobre una copia temporal: estado original, archivo retirado,
restauración, modo ejecutable alterado y restauración. Se usa el revisor real;
no se ejecuta código copiado ni se modifica el checkout original.

El productor conserva streams, código de salida, tiempos e inventarios.
Resultado inesperado o timeout detiene la secuencia y conserva INCONCLUSIVE;
CLI 1 también al verificarlo. Una reparación posterior no puede esconderlo.
Los dos fallos esperados comparten error; solo contrastes completos permiten
las conclusiones limitadas al laboratorio. No se autentica ejecución ni host.

- **2,956 QA PASS**, cero fallos/errores/skips; 2,932 anteriores retenidas en
  los mismos ocho grupos, 24 nuevas. 86 focales PASS.
- SDK real; verificación separada sin SDK de QA/telemetría/preparación PASS.
  Máximo worker 87.837250 s; grupo con las nuevas pruebas 43.022999 s.
- Digest `01e8ff8fe944e7fac50bc049ecaa0a923e668bbf2f816579e4cc4d2487fe3079`.
- 237 archivos Python anteriores idénticos; tres registros modificados y
  tres archivos Python añadidos. Ninguna prueba anterior reescrita.
- Frontera complementaria: 642 históricos intactos. El verificador legado
  devuelve 1, `unreviewed root file`, tanto en #95 como en esta versión.
  Es un bloqueo preexistente de su contrato de raíz; no se presenta como PASS.

Evidencia y aceptación CLI final:
`SUPERHUNTER_DIAGNOSTICO_FALLOS_PROPIOS_20261108.zip`; consultar
`actual-experiment-and-altered-controls/acceptance.json`. Incluye procesos
reales y copias declaradamente alteradas. El control incompleto es un subconjunto
de la captura real, no un timeout ocurrido. Los tests de errores de infraestructura
usan inyecciones identificadas. Ninguna firma o autenticación independiente nueva.

M1 sigue parcial; 1/6 hitos globales cerrados. No reejecuta Slither/Geth/EELS
ni recertifica Rust/PFT/Census. No habilita targets remotos, operación continua,
reparación autónoma del checkout o cambios de permisos fuera de la copia propia.

Siguiente: recuperación de expedientes propios ante interrupción de escritura,
con conservación explícita de estados incompletos y sin promociones a éxito.

Los apartados siguientes conservan sus digests y límites históricos.

## Estado vigente: captura observable de una revisión propia

Sucesor de PR #94, commit `8e39da34033065a203207b1df962a4762de4180e`.
[OWNED_PROCESS_CAPTURE.md](OWNED_PROCESS_CAPTURE.md) documenta el productor
real y el verificador sin ejecución. Un worker fijo, supervisado y de lectura,
revisa este checkout; se recogen salida y terminación reales, dos relojes e
identidad por bytes del intérprete. El origen es observación del propio padre,
no exportación de journald ni autenticación independiente de ejecución.

- **2,932 QA PASS**, cero fallos/errores/skips. 2,906 anteriores conservadas
  en sus mismos ocho grupos, 26 nuevas; 62 focales PASS.
- SDK real en productor; verificación de QA, telemetría y preparación en un
  proceso separado sin SDK PASS. Máximo worker 87.932712 s, límites intactos.
- Digest `fb9ddcc0a9d18c6027a4c19a15598eb74d7b7630dd698a5a23a76b2e28eedc88`.
- 234 archivos Python anteriores idénticos; solo cambian los tres registros
  de entrada/QA, además de añadir módulo, worker y tests. Ninguna prueba previa
  se cambia. La revisión conserva 642 archivos históricos protegidos.

El verificador requiere ancla externa y recomputa el resultado frente al
checkout actual. Las pruebas distinguen captura real y controles alterados:
un reloj editado coherentemente con nueva ancla NO acredita exactitud UTC ni
la ejecución histórica. No se solicita un comando, intérprete o target remoto.

Evidencia y aceptación CLI final:
`SUPERHUNTER_CAPTURA_PROCESO_PROPIO_20261108.zip`; consultar
`actual-capture-and-altered-controls/acceptance.json` para ancla, captura,
comandos, resultados y vencimiento de custodia. Firmar el expediente con una
clave de laboratorio no acredita productor independiente; la clave privada
no se conserva. Los archivos del expediente final fijan también documentos,
por lo que editar el checkout puede invalidar su comparación.

M1 sigue parcial; indicador global sin cambio: 1/6 hitos cerrados. No hay
operación continua, nuevo hallazgo ni cierre de 20 programas. No se repiten
perfiles Slither/Geth/EELS ni se recertifica Rust/PFT/Census en este digest.

Siguiente: captura de un fallo operativo propio y diagnóstico contrastado,
conservando la evidencia de incertidumbre y los límites del proceso fijo.

Los apartados siguientes preservan sus estados y digests históricos.

## Estado vigente: custodia journal y aritmética temporal corregida

Sucesor de PR #93, commit `3e4c36e3bb8de7fc7a66a9f3a17421dc407cec59`.
[JOURNAL_CUSTODY_TIME.md](JOURNAL_CUSTODY_TIME.md) contiene código, controles
y aceptación. Se reprodujeron tres OverflowError con fechas válidas al aplicar
incertidumbre. La comparación exacta con microsegundos enteros conserva
INCONCLUSIVE_ORDER sin recortar intervalos; UTC fuera de rango se rechaza.

El nuevo consumidor revalida firma, journal y contexto temporal declarado.
La custodia válida no promueve orden incierto o contradictorio: CLI devuelve
1 en ambos casos, 0 solo para coherencia declarada y 2 para evidencia inválida.

- **2,906 QA PASS**, 2,874 anteriores en sus mismos grupos y 32 nuevas; cero
  fallos, errores o skips. 70 focales PASS. SDK real y verificación separada
  de QA/telemetría/preparación sin SDK PASS.
- Cuatro registros sintéticos, parsers y firmas reales, 16 comandos por CLI
  con resultados esperados. No se adquirieron logs del host ni se autenticó
  ejecución real. Clave efímera nunca escrita; confianza del propio laboratorio.
- Digest `4656f2218dcc1ad7144686c201c4feffc34dab0d90f90e60788a3185de951f12`.
  Máximo worker 86.534811 s, límites intactos. 230 archivos
  Python anteriores y todas las pruebas previas conservados. 642 históricos intactos.

Evidencia: `SUPERHUNTER_JOURNAL_CUSTODIA_TIEMPOS_20261108.zip`. Los sellos
vencen 24 horas tras emitirse; no atribuir aceptación actual tras caducar.
No se repiten perfiles nativos ni Rust/PFT/Census. M1 sigue sin cierre y
el indicador global permanece en 1/6 hitos cerrados.

Siguiente: captura observable de un proceso fijo de laboratorio con formato
de origen explícito, diferenciando observación propia de exportación journald.
No usar JSON sintético como prueba de adquisición real ni afirmar independencia
del host. Mantener fuera los objetivos remotos y las órdenes arbitrarias.

Los apartados siguientes conservan historia y sus identidades originales.


## Estado vigente: QA, recibos originales y custodia integrados

Sucesor de PR #92, commit `e4380bdd9a38f53296aa70175d3b775ec4e7eaa9`.
[QA_CUSTODY_REPORT.md](QA_CUSTODY_REPORT.md) documenta el consumidor real
que revalida QA, firma de custodia con confianza externa al expediente,
ocho recibos originales y reconstrucción exacta del log. El verificador
regenera el reporte y comprueba nuevamente revocación y caducidad.

- **2,874 QA PASS**, 2,850 anteriores conservadas en sus grupos y 24 nuevas;
  cero fallos, errores o skips. 72 focales PASS. SDK real en productor;
  verificador separado de QA/telemetría/preparación sin SDK PASS.
- Aceptación con QA real y clave efímera de laboratorio: creación, verificación
  separada y revalidación del original PASS; cuatro controles alterados
  rechazados. No se guardó la clave privada. La política pública pertenece
  al laboratorio; no acredita productor independiente ni ejecución autenticada.
- Digest `23497a237e0b3a7be678baef6301196032823049c8560f56576d081e2402b58c`.
  Ocho workers y límites intactos; máximo 84.553009 s.
- 229 archivos Python anteriores intactos; solo cambian los registros de QA
  y la entrada CLI, además de añadir módulo/pruebas. Ninguna prueba anterior
  se reescribió. 642 archivos históricos protegidos intactos.

Evidencia: `SUPERHUNTER_QA_CUSTODIA_INTEGRADA_20261108.zip`. El sello de
laboratorio vence 24 horas tras emitirse; los controles de vigencia permanecen
activos. Tras vencer no atribuir una aceptación actual al reporte archivado.

No se reejecutaron perfiles nativos Slither/Geth/EELS; sus evidencias conservan
sus digests originales. Rust/PFT/Census no recertificados. No cierra M1 ni
ningún nuevo hito global; permanece 1/6 hitos cerrados.

Siguiente: recepción de journal propio con custodia y contexto temporal
explícito, conservando incertidumbre del reloj y separando vínculo por bytes
de autenticación de ejecución. No habilitar fuentes remotas ni escaneo.

Los apartados siguientes conservan historia y sus identidades originales.


## Estado vigente: contrato cerrado de telemetría QA

Continuación de PR #91, commit `c2ab7c9ee0b4cbf0266ecf03defc1489521cc072`.
[QA_TELEMETRY_SCHEMA.md](QA_TELEMETRY_SCHEMA.md) contiene implementación,
reproducción, resultados y límites. El adaptador comparte validación entre
producción y lectura, normaliza tipos de error y crea spans sin recursos del
entorno ni captura automática de excepciones. Control antes/después con SDK
real y datos sintéticos confirma la corrección, conservando QA_FAILED.

- **2,850 QA PASS** con SDK real; 2,833 previas en sus mismos grupos y 17 nuevas.
  Verificación separada sin SDK PASS; ocho recibos originales cotejados y log
  agregado reconstruido. Cero fallos, errores o skips.
- 44 pruebas focales PASS con SDK; 17 nuevas en entorno sin SDK comprueban
  también el bloqueo de dependencia. Doce payloads antiguos aceptados por
  esquema; esto no recertifica sus ejecuciones.
- Digest: `4be4033a4757c919cc88fef6273bbf482ab2dd4c6cfa4909efdb7a87ccc18b25`.
  Ocho workers y presupuestos intactos; máximo 84.197994 s.
- 227 archivos Python anteriores intactos; cambian el adaptador y dos registros
  QA, se añaden esquema y pruebas. Ninguna prueba previa fue reescrita.
- Límite de repositorio PASS, 642 archivos históricos preservados. No se
  reejecutaron perfiles nativos ni Rust/PFT/Census para este digest.

Respaldo: `SUPERHUNTER_TELEMETRIA_ESQUEMA_CERRADO_20261108.zip`. Collector
continúa pendiente. Este cierre acotado no completa otro hito M0–M5 ni prueba
operación 24/7. La medición global previa de 1/6 hitos cerrados no cambia.

Siguiente trabajo: revisar el flujo integrado de M1 para evidencia de procesos
propios, custodia y reporte local; fijar una aceptación con rechazo de capturas
incompletas o alteradas. No habilitar objetivos arbitrarios ni exportación de red.

Los apartados siguientes conservan historia y sus identidades originales.


## Estado vigente: estudio pareado de tiempos cerrado

Se completaron las 24 corridas previstas sobre PR #90, commit `b35feb7b87f3833c99806f38a945666e278659dc`, sin cambiar código, dependencias, pruebas ni límites. El [estudio de tiempos de QA](OWNED_QA_TIMING_STUDY.md) contiene los resultados, las anclas y la revisión reproducible. Esta entrega es documental; su digest ejecutable sigue siendo `7b8e6779373bb4cc21f81015865feb5de82a9acc268f4163a1475e99f29b0980`.

- **24/24 corridas PASS**, 2,833 pruebas por corrida: 67,992 ejecuciones repetidas de 2,833 identidades distintas, con los mismos ocho grupos.
- Revisión independiente sin SDK PASS: 24 expedientes QA, doce de telemetría, 192 recibos originales y 24 logs reconstruidos. La revisión lee y recalcula evidencia, sin reejecutar QA.
- Mediana base: 380.502 s; adaptador: 379.348 s. Mediana de diferencias pareadas: -1.614 s y -0.424%. Las diferencias tienen ambos signos y no identifican un costo causal del SDK.
- El p95 empírico, con doce muestras por modo, es el máximo observado; no acredita una cola poblacional o un SLO. Se documentan la pausa intermedia y el ruido del host no controlado.
- Evidencia: `SUPERHUNTER_MEDICION_QA_24_CORRIDAS_20261108.zip`. La omisión histórica, los catálogos y sus denominadores permanecen. Collector sigue pendiente; avance global no determinado.

Siguiente: esquema cerrado de telemetría de QA y pruebas locales de redacción con datos sintéticos antes de diseñar exportación. Los apartados siguientes conservan las entregas anteriores y sus resultados propios.

## Contrato correcto y aceptación nativa de PR #90

Esta continuación parte de PR #89, commit
`cb83d677f9a45a57c386e821c9604498c4fd5208`, y añade el perfil separado de
[contrato correcto y contra-controles en dos EVM](OWNED_CORRECT_TWO_EVM.md).
Geth y EELS ejecutan exclusivamente la fuente correcta sobre los 16 casos
fijos (13 secuencias distintas). Se comprueban decisiones, efectos, permisos,
generaciones y estado de cada evento, con expectativas explícitas e historial.

Digest: `7b8e6779373bb4cc21f81015865feb5de82a9acc268f4163a1475e99f29b0980`.
Evidencia: `SUPERHUNTER_CONTRATO_CORRECTO_DOS_EVM_20261107.zip`.

- 36 pruebas focalizadas PASS (34 nuevas y dos regresiones existentes de CLI).
  Un primer pase focal tuvo dos fallos por una referencia al nombre de
  componente incorrecto; se corrigió la referencia, conservando las pruebas.
- Perfil nuevo con Geth/EELS real y repetición en otro proceso PASS. Por motor:
  dos compilaciones, 32 constructores y 116 llamadas, incluidas 32 sondas de un
  gas que no cambian estado. Las 42 observaciones del modelo conservan once
  usos aceptados y siete rechazados. Motores y repeticiones no amplían muestras.
- QA con SDK real: **2,833 PASS**, cero fallos, errores o skips; las 2,799
  anteriores permanecen en sus mismos grupos. QA, telemetría y preparación
  verificadas por otro proceso sin SDK. Ocho workers y límites intactos;
  máximo 81.162 s. Permanecen sin cambios 221 archivos Python anteriores;
  se modifican expresamente tres archivos de registro de entrada/QA.
- Slither nativo y replay para este digest: TP1/TN2/FP0/FN0. Geth/EELS histórico
  y verificación independiente PASS: cuotas TP4/TN2/FP0/FN0; autoridad temporal
  TP6/TN4/FP0/FN1. `latent_revocation` sigue presente en ese perfil histórico.
- Se regeneraron y verificaron mediante CLI los informes actuales de cobertura
  histórica/adicional, su vínculo, el inventario y el modelo correcto. Las trazas
  del modelo coinciden con las del perfil nativo adicional para este digest.
- Límite de repositorio PASS y 642 archivos históricos intactos. Rust/PFT/Census
  no reejecutados ni recertificados.

El perfil nuevo no ejecuta variantes defectuosas ni detectores; no se calculan
TP/TN/FP/FN para él. No prueba autenticación real de principales o credenciales,
independencia de host o la semántica completa de EVM. No se mezclan sus casos
con los históricos. Avance global no determinado; plataforma incompleta.

Siguiente trabajo: medir el tiempo del adaptador OpenTelemetry sobre este
código congelado frente al mismo QA con igual número de verificaciones,
mediante doce pares de corridas de orden alternado. Aún no hay resultados de
ese estudio en esta entrega; sus datos y límites se documentarán por separado.

## Comportamiento correcto aceptado en #89

Esta continuación parte de PR #88, commit
`050595cdd130d8e574a56f2a6531dac30eecc2a8`, y añade el
[comportamiento del modelo correcto](OWNED_CORRECT_BEHAVIOR.md) sobre los
16 contra-controles fijos. Una tabla explícita y una referencia de historial
comprueban decisiones y efectos del modelo. Son 42 eventos: 11 usos aceptados
y siete rechazados; los otros 24 eventos son comandos de control.

Digest: `9a6f4216ccfe81baf689882da09c1a5f32cf2353bc605b79bd56074fb6a5e604`.
Evidencia: `SUPERHUNTER_COMPORTAMIENTO_CORRECTO_20261107.zip`.

- 31 pruebas focalizadas PASS (29 nuevas más dos regresiones existentes de
  entradas CLI). El primer pase completo falló esas dos regresiones: el registro
  se había añadido después del arranque de la CLI directa. Se corrigió su orden;
  el intento rechazado y sus recibos se conservan. No se eliminaron pruebas.
- QA corregido con SDK real: **2,799 PASS**, cero fallos, errores o skips;
  las 2,770 anteriores permanecen en sus mismos grupos. Verificación de QA,
  telemetría y preparación desde otro proceso sin SDK PASS.
- CLI de creación y verificación del comportamiento en procesos separados PASS.
  Ocho workers y límites intactos; máximo 78.921 s. Se preservan 219 archivos
  Python anteriores; solo cambian los tres registros de entrada/QA.
- Slither nativo y replay para este digest: TP1/TN2/FP0/FN0. Geth/EELS histórico
  y verificación independiente PASS: cuotas TP4/TN2/FP0/FN0; autoridad temporal
  TP6/TN4/FP0/FN1, conservando `latent_revocation` y sus denominadores.
- Límite de repositorio PASS y 642 archivos históricos intactos. Rust/PFT/Census
  no reejecutados ni recertificados.

El perfil nuevo ejecuta únicamente el modelo correcto; no ejecuta contratos,
variantes defectuosas o detectores ni recalcula métricas históricas. El éxito
nativo anterior de este digest pertenece a sus perfiles históricos separados.
Avance global no determinado; plataforma incompleta.
Siguiente: comprobar el mismo contrato correcto y los contra-controles fijos
en dos motores EVM, con decisiones, efectos y estado de permisos por evento.

## Inventario de registros aceptado en #88

Esta continuación parte de PR #87, commit
`7a57b3538218a4f981ef5001f35f764be0b467b2`, y añade el
[inventario verificable de registros](PORTFOLIO_INVENTORY.md). Valida las 50
identidades del catálogo externo y sus cinco desgloses, vincula esos seis JSON
al digest de QA y conserva separados los cuatro registros documentales.

Digest: `1603e987090e96dddcd265f5586b63fe85d7742331534da77fb966c32fc4170a`.
Evidencia: `SUPERHUNTER_INVENTARIO_REGISTROS_20261107.zip`.

- 32 regresiones focalizadas PASS; CLI de creación y verificación en procesos
  separados PASS. Los nueve archivos de catálogo mantienen exactamente sus
  bytes de #87; no se promueven sus estados ni se infieren instalaciones.
- QA completo con SDK real: **2,770 PASS**, cero fallos, errores o skips;
  32 nuevas y las 2,738 anteriores conservadas en sus mismos grupos. QA,
  telemetría y preparación verificadas desde otro proceso sin SDK.
- Ocho workers y límites intactos; máximo observado 77.482 s. Slither nativo y
  replay PASS sobre este digest: TP1/TN2/FP0/FN0 en sus tres controles fijos.
- Geth/EELS y verificación independiente PASS para este digest: cuotas
  TP4/TN2/FP0/FN0; autoridad temporal TP6/TN4/FP0/FN1. `latent_revocation`
  permanece. Límite de repositorio PASS y 642 archivos históricos intactos.
  Rust/PFT/Census no reejecutados ni recertificados.

Los conteos 27/50/25/50 son unidades distintas. La estructura de un registro
no prueba la implementación declarada. El SDK OpenTelemetry usado en QA no
acredita el Collector #26. Avance global no determinado; plataforma incompleta.
Siguiente: comprobar decisiones y efectos del modelo correcto sobre el corpus
adicional fijo, sin reescribir los casos o métricas históricas.

## Vínculo de cobertura aceptado en #87

Esta continuación parte de PR #86, commit
`2ce05781977ad0036c19e78b9b17bee2c04a0bf2`, y añade el
[vínculo verificable de cobertura](OWNED_COVERAGE_LINK.md). Regenera los dos
expedientes mediante sus verificadores reales, exige el mismo código y dos
anclas externas, y vuelve a comprobar inventarios y bytes al terminar.

Digest: `bd55723e437f960ece6eb033f2c5ca8fe826c013b23257e2c9a90470fd75ac88`.
Evidencia: `SUPERHUNTER_VINCULO_COBERTURA_20261107.zip`.

- 32 regresiones focalizadas PASS; CLI de creación y verificación en procesos
  separados PASS sobre los expedientes generados para este digest.
- QA completo con SDK real: **2,738 PASS**, cero fallos, errores o skips;
  32 nuevas y las 2,706 anteriores conservadas en sus grupos. QA/telemetría y
  preparación verificadas en un proceso sin SDK. Ocho workers y presupuestos
  intactos; máximo 77.449 s. El vínculo mantiene separados los once casos
  históricos y los 16 contra-controles; no ejecuta un detector.
- Slither nativo y replay: TP1/TN2/FP0/FN0 sobre sus tres controles fijos.
- Geth/EELS y verificación independiente PASS para este digest: cuotas
  TP4/TN2/FP0/FN0; autoridad temporal TP6/TN4/FP0/FN1, con `latent_revocation`
  conservado. Límite de repositorio PASS y 642 archivos históricos intactos.
  Rust/PFT/Census no reejecutados ni recertificados.

La cobertura adicional conserva el hueco del histórico y su omisión conocida.
Los hashes identifican bytes; no autentican productores ni acreditan que se
detectaron vulnerabilidades nuevas.

## Corpus de contra-controles aceptado en #86

Esta continuación parte de PR #85, commit
`a296e91a3cd33581ef1fbccb10dca037ce28ea20`, y añade el
[corpus v1 de contra-controles de cobertura](OWNED_COVERAGE_COUNTER_CONTROLS.md):
16 casos declarados, 13 secuencias distintas y ocho pares presencia/ausencia.
Los índices esperados se contrastan con los dos algoritmos de cobertura.
Los once casos históricos y sus etiquetas conservan su hash fijado.

Digest ejecutable de esta continuación:
`5bdc53488ded562178e7e7bc3799bf771fa48b05e922c9eaefc0b13b0ff4e6f7`.
La evidencia se entrega en `SUPERHUNTER_CORPUS_COBERTURA_V1_20261107.zip`.

- 52 pruebas focalizadas PASS, incluidas las 22 previas. El primer pase encontró
  un fallo por referencias compartidas entre eventos; se corrigió la copia por
  ocurrencia sin cambiar los valores ni hashes del corpus.
- QA con SDK OpenTelemetry real: **2,706 PASS**, cero fallos, errores o skips;
  30 regresiones nuevas y 2,676 identidades previas conservadas en sus mismos
  grupos. Expedientes y preparación verificados en un proceso sin SDK.
- Creación y verificación de los dos perfiles de cobertura en procesos separados.
- Slither nativo y replay sobre el nuevo digest: TP1/TN2/FP0/FN0, tres controles
  propios fijos, sin atribuirles precisión general.
- Geth/EELS y verificación nativa en proceso separado PASS sobre el nuevo
  digest: cuotas TP4/TN2/FP0/FN0; autoridad temporal TP6/TN4/FP0/FN1.
  La omisión `latent_revocation` y los denominadores permanecen separados.
- Límite de repositorio PASS, 642 archivos históricos intactos; 212 archivos
  Python previos sin cambios. Ocho workers y presupuestos conservados;
  máximo observado 75.687 s. Rust y PFT/Census no reejecutados ni recertificados.

El nuevo informe describe entradas. No ejecuta los casos adicionales como
modelos o contratos ni calcula métricas de detección para ellos. Expone las
secuencias duplicadas y compartidas; no suma denominadores con el histórico.

## Aceptación anterior de #84

La cabeza ejecutable aceptada por el cierre de #85 fue PR #84, commit
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

Verificar la consistencia del catálogo documental externo de 50 repositorios
con sus cinco desgloses. Incorporar sus fuentes de datos al inventario fijado
de QA y mostrar los conteos de los cuatro registros estructurados por separado:
27 requisitos, 50 capacidades internas, 25 iniciativas y 50 candidatos externos.
Usar los validadores internos existentes, sin inferir que una entrada de
catálogo es una integración, que un SDK es un Collector o que el número de
tests equivale al porcentaje global de capacidad. No cambiar estados por
presencia de herramientas o aceptaciones de laboratorio acotadas.

La plataforma sigue incompleta; avance global no determinado, ninguna
vulnerabilidad original confirmada ni operación 24/7 en 20 programas acreditada.
