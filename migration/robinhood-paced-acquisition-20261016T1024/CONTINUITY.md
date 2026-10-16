# Relevo: limitador global publicado; captura real pendiente

Repositorio único: `josuechavando350-png/nexus-quant-capital`. Leer AGENTS.md,
README y buscar PR/commits posteriores antes de continuar. Rama de resultados:
`nqc/paced-acquisition-20261016T1024`, sobre PR16
`a6c356ad6379d51683a07f0c67bbd280eb1ec5bf`. No fusionar automáticamente.

## Incremento cerrado el 16/oct/2026

**Offline solamente: 0 métodos RPC reales, 0 segundos de captura.**
No se volvió a consultar después del 429 histórico, ni se reejecutó su runner.
No existe todavía `evidence/pilot/` en este incremento.

Protocolo publicado **`f82249cd9844d686b13e637b5d22a7eca88985d1`**, árbol
`046c0610fe5dac09ece21a35531e5d9aaa324bef`, rama
`nqc/paced-protocol-20261016T1024`. Coincidencia exacta con árbol local.
57 fuentes fijadas por `registration-sources.json`. NO regenerar política/lock
ni editar código registrado antes de la captura: si aparece un defecto, requiere
protocolo nuevo y publicación anterior a consultas.

Nuevo `pacing.py`: separación mínima global de 350 ms entre inicios locales de
despacho; sin crédito acumulable, reloj inyectable, ninguna petición posterior
a error. Gate, contador, bytes y plazo sobreviven la rotación fría planificada.
Las esperas cuentan en el plazo global. Rechazo previo a RPC si la próxima
admisión ya no cabe; al despertar se comprueba de nuevo el plazo. Se preserva
cada intento en `admissions.json`, incluido el que no llegó a enviarse.

Nuevo lector y auditor: latencia primaria desde ANTES de admisión de cabecera
hasta verificación canónica; secundaria desde despacho HTTP local. Doce rondas,
sin eliminación de lentas o cabeceras repetidas; registrar cadencia entre
admisiones de cabecera. Una cadencia de tres peticiones requiere >=1.05 s bajo
esta política, aunque una ronda aislada podría ser menor. No prometer subsegundo.
La separación local no demuestra la cuota/ventana de llegada del proveedor.

**114 pruebas Python aprobadas**: 22 para el nuevo flujo (12 regresiones portadas
y 10 casos específicos), más 92 anteriores. Fallos sintéticos auditados en las
59 fronteras RPC. Cuatro trazas artificiales completas conservadas:

- Éxito: 59 peticiones simuladas, 12 rondas; gap mínimo 350 ms, 700 ms desde
  despacho vs **1,050 ms incluyendo admisión**, once intervalos de 1,050 ms.
- Cuota artificial: parada en petición 10; conserva segmento válido de 10 bloques.
- Plazo de 1 s: 3 peticiones, cuarto intento no enviado, ningún target congelado.
- Plazo de 9 s: 26 peticiones, intento 27 no enviado; conserva índice y una ronda.

Esas cifras NO son resultados de Robinhood. Los registros sintéticos usan cuentas,
estado y relojes artificiales; no convertirlos en cobertura, candidatos o dinero.
`evidence/offline-summary.json` y cada `evidence/synthetic/*/audit.json` contienen
resultados/hashes. PR16 reproducido con su auditor original conserva parada real,
10 RPC y cero observaciones; manifiestos PR13/14/15/16 intactos (210/175/77/38
archivos). 377 blobs originales, 106 workflows deshabilitados, cero activos.
Rust/Solidity sin cambios y no reejecutados. No se certificó la suite global
histórica del repositorio. Confianza alta en invariantes offline, no en ingresos.

## Fuente actual SIN CAMBIO

`migration/robinhood-acquisition-20261016T0922/evidence/pilot/registry.json`

Raíz: `c57a798823c6163a54588353b92269fd98cd050cc96c9afb6123741d6752f7de`.
SHA del archivo: `67d8a5c619bf025e410e785838e9f08b5919a6e844112eb22911b17369c501ee`.
Prefijo `valid_prefix`: 88,646,281–89,912,197, 1,265,917 bloques, 57 Borrow,
30 cuentas. No cohorte congelada. No usar ningún registro sintético como fuente.
Revalidar checkpoint e inicio; continuar SOLO desde **89,912,198**. Recalcular
anchor vigente. No retroceder a PR14 ni repetir 10,000 bloques confirmados.
Historia anterior pendiente para otro lote: 88,246,281–88,646,280.

## Próxima ejecución acotada

1. Verificar PR/commits y que otro proceso no esté capturando ni haya generado
   `evidence/pilot`. Verificar fuentes registradas y dependencias exactas PR15.
2. Ejecutar UNA captura con el protocolo ya publicado, presupuesto TOTAL de
   512 métodos/900 s, incluyendo actualización de cola, autenticación, esperas
   y doce rondas. Target nuevo, límites canónicos y sin huecos. Conservar cuentas
   con deuda cero. Selección independiente de salud/liquidaciones.
3. Congelar solo tras target completo/autenticado. Reconciliar posiciones contra
   `totalBorrowShares` en cada hash. Retener frío, reutilizados y todas las rondas.
4. Nuevo 429/error/denegación: parar TODO sin reintento, rescate o endpoint
   alternativo. Preservar cuerpo, prefijo y ausencia de observaciones si procede;
   no publicar cero candidatos cuando no se observaron. No sustituir captura.
5. Auditar, comprobar hashes, redactar resultados y publicar rama/PR borrador.
   No sobrescribir estas trazas/reglas/README prerregistrados: añadir informe
   de captura nuevo y actualizar continuidad sin cambiar el protocolo.
6. Si hubo candidatos, siguiente estudio de supervivencia y ciclo completo
   AA/EntryPoint/bundler/paymaster/Nitro/DA, fallos/costes y patrocinio prepagado.
   Captura repetible con margen neto, financiación y admisión siguen pendientes.

Comandos desde raíz del repo (dependencias locales si persisten):

```bash
export PYTHONPATH=/workspace/scratch/f9e56e91df85/nqc-http-deps
python -m unittest discover -s migration/robinhood-paced-acquisition-20261016T1024 -p 'test_*.py' -v
python migration/robinhood-paced-acquisition-20261016T1024/paced_acquisition.py --out migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot --registration-commit f82249cd9844d686b13e637b5d22a7eca88985d1
python migration/robinhood-paced-acquisition-20261016T1024/audit_paced.py migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot --out /tmp/nqc-paced-live-audit.json
```

El segundo comando está preparado, **NO ejecutado** en este relevo. Tras error
el proceso sale 1: no confundir ese estado preservado con razón para relanzar.
`verify_offline.py` se ejecutó para las 114 pruebas y verificadores; sus recibos
están publicados. No regenerar `build_offline_evidence.py` en las carpetas
existentes: deliberadamente exige salidas nuevas para no pisar evidencia.

Worktree `/workspace/scratch/f9e56e91df85/nqc-paced-review`, Python 3.12.14.
Recuperar GitHub si desaparece el entorno. Transporte y versiones fijados PR15,
sin nuevas dependencias. APIs de reloj/sleep verificadas en documentación primaria
Python 3.12 (en README); comprobar nuevas APIs si se añaden.
Único endpoint `https://docs-demo.robinhood-mainnet.quiknode.pro/`.
TLS/proxy/no_proxy/CA intactos; nunca mostrar URLs privadas o credenciales.

No trading, firmas, transacciones, claves, gastos, suscripciones o despliegues.
No tocar nexus-engine, Cano, clientes, dominios o workflows. No crear tareas
duplicadas, reactivar tareas antiguas ni afirmar autorreparación no observada.
Objetivo comercial pendiente: completar este incremento no demuestra monetización.
