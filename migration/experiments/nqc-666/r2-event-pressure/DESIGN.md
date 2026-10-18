# NQC666 R2 — recuperación determinista bajo presión de eventos

## Alcance y origen

Este experimento continúa R1, commit
`fef142e0310c72ebc1f634e5b5c3f445fe6c4b4e`, sin modificar sus archivos. Conserva el
límite de **256 posiciones** y el propietario único. No añade hilos, colas,
servicios, dependencias Rust externas, RPC ni gastos. No prueba cobertura a escala
de todos los mercados. Los 18 roles de NQC666 siguen siendo responsabilidades
lógicas, no 18 procesos.

La función financiera y los guardianes finales se importan directamente de
`nqc666::engine::guard`; la aritmética y validación de snapshots se importan de R1.
`prepared.rs` es una copia byte-idéntica necesaria para acceder al constructor
interno `from_screen`. `PROVENANCE.json` registra cada origen y transformación;
`evidence/engine.rs.patch` muestra la diferencia completa respecto al motor base.

## Dos cambios independientes

**Escritura única del ranking.** El motor original pone primero a cero la prioridad
y después escribe el valor nuevo, recorriendo dos veces los ocho ancestros. En un
evento válido, R2 puede escribir directamente el resultado final. Primero elimina
la entrada anterior e incrementa la generación como antes. Si falla la identidad
o se agota la generación, pone la prioridad a cero antes de devolver el error.
Los errores del guardián producen prioridad cero al finalizar el evento.

No hay callbacks, concurrencia ni puntos de suspensión entre ambas operaciones.
Ningún llamador puede obtener un ticket en ese intervalo. La optimización depende
de ese contrato: introducir concurrencia o código externo en `apply` exigiría
revisar de nuevo la prueba. Se mantienen todos los cálculos económicos y defensivos.

**Recuperación por lote.** El selector original elimina líderes vencidos uno por
uno; cada uno requiere actualizar ocho ancestros. R2 conserva ese camino hasta
64 descartes. Si el siguiente líder ya es válido, devuelve el ticket normalmente.
Sólo si también es inválido activa dos barridos y reconstruye el árbol.

1. Encuentra el mayor ranking aún válido entre las hojas restantes.
2. Borra exclusivamente los rankings que preceden a ese ganador; si no existe
   ganador, borra todos los rankings positivos.
3. Reconstruye los 255 nodos internos de abajo hacia arriba.

Cada ranking ordena primero por puntuación descendente y luego por slot ascendente.
Una hoja que no puede superar al mejor válido ya visto no necesita comprobar su
vigencia durante el primer barrido.

## Por qué la recuperación preserva la semántica

Sea W el mayor ranking válido. El selector original visita, y elimina, exactamente
los inválidos anteriores a W. Ningún ranking anterior a W puede ser válido, porque
contradiría que W sea el mayor válido. Por tanto, el segundo barrido elimina el
mismo conjunto. Si no hay W, ambos eliminan todos los rankings positivos.

Los inválidos posteriores a W permanecen. Borrarlos anticipadamente cambiaría el
estado observable si el reloj proporcionado retrocediera y el ganador desapareciera
por otro evento. Una prueba dedicada mantiene un ganador en el slot 96, elimina
después ese ganador y comprueba que el slot 97 vuelve a ser seleccionable al
retroceder el tiempo. También se prueban empates y todos los tamaños de ráfaga.

La recuperación modifica rankings, no entradas, generaciones ni tickets. La
finalización vuelve a ejecutar el guardián financiero original. Un ticket de otra
generación, entrada eliminada o ancla diferente sigue rechazado. La admisión
comercial permanece incondicionalmente falsa.

## Ablación y decisión

Los parámetros de compilación permiten medir por separado `BULK` y `SINGLE_WRITE`:

| Variante | Recuperación | Escritura única |
|---|---|---|
| original | Código base importado | No |
| batch | Sí | No |
| single | No | Sí |
| combined | Sí | Sí |

No se infiere el efecto de una técnica a partir del resultado combinado. La versión
piloto con umbral 16 fue rechazada por su regresión visible con ráfagas pequeñas.
Sus fuentes y ocho corridas se conservan. La nueva matriz incluye 65 expiraciones
para revelar el coste justo por encima del umbral 64.

Una mejora en la mediana o en una carga concreta no garantiza dominar las colas,
ni demuestra el mejor umbral para otra CPU o distribución. La recomendación de
uso experimental se basa en los resultados completos de `REPORT.md` y `RESULTS.md`.

## Tres ventanas medidas

| Ventana | Incluido | Preparado antes del reloj |
|---|---|---|
| select | Selección, descarte/recuperación, ticket y guardián final completo | 256 eventos, cálculos de protocolo, fixtures, elección del índice |
| cycle | Copia y aplicación de 256 updates, controles por evento, selección y guardián final | Updates ya decodificados y con deuda/capacidad calculadas; elección del índice |
| pipeline | Lookup, copia, matemática U256/validación R1, un evento, selección y guardián final | Fixture sintético de snapshot y selección del índice |

El resultado completo y una referencia mutable al motor pasan por `black_box`
antes de parar el reloj; el checksum consume todos los campos de salida después.
La barrera mutable hace observables las escrituras del árbol, aunque una consulta
posterior todavía no las utilice. Los supervivientes y los valores económicos
varían, y se exige más de una salida observada durante el calentamiento.

Cada medición es una ventana individual, no un promedio de lote. `cycle` contiene
256 eventos por definición: su tiempo es el ciclo completo y **no** se presenta
dividido entre 256 como latencia individual. Las ráfagas de 256 vencidos sin
superviviente se verifican funcionalmente; la medición principal usa hasta 255 para
observar un ganador variable y la defensa financiera final en cada muestra.

## Límites de defensa y alcance

Se conservan los controles existentes de identidad, vigencia, gas, nonces,
dependencias, pagos, financiación residual, ausencia de capital personal,
slippage y beneficio. Su presencia no autentica los datos suministrados:
financiación/no recurso siguen siendo afirmaciones de fixtures.

No se ha añadido prueba de stateRoot/storage/code, ejecución de IRM, testigo canónico,
ruta real, parsing de red, simulación de liquidación completa, builder, inclusión
Ethereum ni autorización comercial. Tampoco se ha probado cold cache forzada,
NUMA físico o más de 256 posiciones. Estos pendientes continúan explícitos y no se
resuelven con una mejora del selector. NQC031/032 siguen siendo frentes separados.
