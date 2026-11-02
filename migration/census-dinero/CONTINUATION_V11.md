# NQC Shadow v11 — continuación del 1 de noviembre de 2026

## Punto de partida y resultado de este cambio

Fuente: `feat/census-dinero-20261024@3560f74341f485e81e1807405cd4552a0cfea1ae`.
Evidencia histórica: `census-dinero/resultados@e0c6c4bd5c2ee852cb84de72e4a572febc140033`.
Última corrida original: `40349833440`, finalizada el 26 de octubre.

El acumulador original restaba un tiempo de decisión medido desde la notificación del
log a una ventana que empezaba en la notificación del hash de la transacción del oráculo.
También usaba una mediana de corrida cuando faltaba el tiempo individual, con un índice
de actualizaciones compartido entre corridas. Eso no permite acreditar una medición por
evento con un mismo origen temporal.

v11 conserva los datos históricos y registra `flash.ws_decision` para las observaciones
nuevas. El acumulador une esa evidencia a la actualización de la misma corrida, mercado,
bloque y transacción. Los valores anteriores quedan como escenario aproximado, fuera de
la muestra de revisión. Se deduplica por transacción e índice de log, se exponen conflictos
y líneas inválidas, y se registran hashes SHA-256 de los archivos leídos.

## Resultado histórico reproducido

Ver `evidence/continuation-v11-20261101/ACUMULADO.md` y `acumulado.json`:

- 13 corridas; 23.3 horas sumadas de ventanas, sin afirmar continuidad.
- 6 liquidaciones ajenas observadas; 5 directas; 2 clasificadas como peleables.
- 1 peleable con ventana de WebSocket registrada; bono inferior a US$1.
- 0 casos con bono de al menos US$1 y ventana medida. Muestra v2: 0/20.
- 0 duplicados y 0 líneas inválidas en las entradas históricas leídas.
- Ninguna captura o rentabilidad de NQC demostrada por este análisis.

## Validación física local

- Base sin cambios: 311 pruebas aprobadas.
- Versión v11: 322 pruebas aprobadas, 0 fallos, 0 omisiones.
- Casos nuevos: separación log/hash, uniones entre corridas rechazadas, mercado/bloque/
  tiempos incompatibles, duplicados, conflictos, entradas incompletas, ventanas perdedoras
  conservadas y meta de 20 sin convertirla en certificación económica.
- `python3 check_isolation.py`: aprobado. 531 fuentes importadas preservadas y 106
  workflows históricos deshabilitados; solo sigue activo el workflow del Census.
- `git diff --check`: aprobado.
- `python3 -m census_dinero plan --run-json run.json`: shadow vivo, replay desactivado.
- No se ejecutaron pruebas Rust/Solidity ni EVM: no se modificó ese código. No se
  verificaron los objetos del repositorio original (`original_objects_checked=false`).

## Observación acotada preparada

El `run.json` inicia una sola observación de 330 minutos, con el libro guardado y los
mismos 19 mercados Base/Morpho. Mantiene umbrales diagnósticos de US$0.05/US$0.02; la
muestra acumulada exige US$1. No repite el replay histórico, que permanece en la corrida
original. Conserva el envío supuesto de 20 ms, explícitamente sin medir envío real.

El workflow existente publica avances cada diez minutos y, al terminar, guarda el
informe individual y `acumulado/` tanto bajo la corrida como en `shadow/ultimo/`.
`fuentes.txt` identifica el productor y el commit leído de resultados. No se agregaron
workflows, suscripciones pagadas, permisos, firmas ni operaciones de fondos.

## Próxima decisión

1. Comprobar arranque real, fuente del libro, suscripciones y publicación de evidencia.
2. Al finalizar, leer los informes y contar casos nuevos válidos, ventanas perdedoras,
   inconsistencias y coste de observación. No extrapolar rentabilidad de una ventana corta.
3. Si la muestra sigue incompleta, decidir una siguiente observación acotada con evidencia;
   no existe un proceso perpetuo ni una garantía de completar 20 casos en esta corrida.
4. Siguen pendientes la economía de la ruta propia, inclusión/envío reales y las 12 cadenas
   incompletas del Census ampliado. Este cambio no declara Census o Shadow certificados ni
   autoriza Canary.

Veinte eventos solo habilitan una revisión. Pueden compartir bloque, día o movimiento de
mercado y no constituyen automáticamente veinte observaciones estadísticamente independientes.
