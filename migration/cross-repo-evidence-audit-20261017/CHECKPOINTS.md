# Auditoría NQC / nexus-engine — Checkpoints append-only

## Checkpoint inicial — 2026-10-17 UTC

**Alcance:** repositorios leídos por conector GitHub; cero operaciones, gastos, firmas, despliegues, workflows o cambios de rama principal.

### Hechos nuevos verificados

- nexus-engine main `380eff1fc14336bd24d93c8ef807525a7078950d` tiene árbol principal de 3,353 entradas; actualmente contiene proyectos ajenos a NQC y NQC histórico T35–T38.
- NQC main `16e352225ba8a6a931834c4edf3d86d9a2924b7d` es importación aislada; otras 44 ramas y 26 PR en borrador constan en inventario previo. Se preservaron líneas Morpho y Robinhood sin fusionarlas.
- PR730 Aave Multicall3 reporta **11.3288x** aceleración en un conjunto de nueve cuentas; no confundir con **11 µs**. Archivo original de microsegundos todavía no localizado.
- T37: 50k mercados sintéticos / 250k superficies / 1m señales; no latencia productiva certificada. Census: 523,424 filas de pools V2; 1,045,459 fuentes de capital NO son mercados.
- Aave one-shot local: 2,273.989378 USDC antes de gas; Morpho Robinhood/Nitro: 32.060665 USDG antes de gas; Morpho Ethereum B: residual matemático externo 0.001651296044494913 ETH sujeto a obligaciones desconocidas. Ninguno es P&L realizado NQC.
- Consulta a memoria histórica de conversaciones no localizó fuente exacta de 11 µs ni «14,000 billones». Hay que ampliar la búsqueda en ramas/artefactos.
- Tarea automática de auditoría: habilitada por hora, primera ejecución aún no constatada; notificaciones push/email desactivadas.

### Pendientes por prioridad

1. Localizar benchmark original de 11 microsegundos: rama/archivo/run/artifact, CPU, método, muestra, unidad y etapa. No elevar marca sin muestra cruda.
2. Rastrear cita «14,000 billones» en código, informes, PRs y cálculos, verificando sistema de numeración y si es principal, TVL, señal sintética o valor de mercado.
3. Revisar más ramas originales NQC Engine (CI/replays), actualizar tabla de módulos sin duplicados y señalar código NQC que aún no migró.
4. Comparar 3 rutas comerciales con gastos verdaderos, financiación no recursiva/no-recourse y carrera de captura, sin hipótesis de dinero ganado.
5. Incorporar nuevas pruebas documentales a AUDIT_STATUS.md con commit/scope exactos y anexos pequeños cuando justifique.

### Siguiente ciclo

Comprobar el último commit de esta rama, consultar fuente original de benchmark en ramas históricas y exactitud de magnitudes gigantes. Si GitHub, permisos o tiempo lo impiden, dejar bloqueo fechado en este archivo. No sobrescribir esta entrada.
