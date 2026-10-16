# Relevo: adquisición completa medida; ampliar cobertura antes de inferir negocio

Único repositorio: `josuechavando350-png/nexus-quant-capital`. Buscar primero
PR/commits posteriores; leer AGENTS.md, README y este relevo o sucesor.
Rama de resultados `nqc/paced-capture-20261016T1117`, sobre PR17
`ff64ca270e82d7faba58ee4f4024cac207e8bfb3`. Mantener PR borrador, no fusionar.

Evidencia publicada en **`55c01549da02f6374e04ac731def795ab81e21ae`**, árbol
`31fc8d2e95fa0ee192c6398567eb6ce69cc11259`, rama
`nqc/paced-capture-evidence-20261016T1117`. El commit posterior solo incorpora
este relevo y su manifiesto. Protocolo previo inalterado:
**`f82249cd9844d686b13e637b5d22a7eca88985d1`** (PR17).

## Captura real TERMINADA

16/oct/2026 **11:19:21.046–11:19:58.633 UTC**: 89 métodos RPC/89 HTTP,
37.587 s de journal, 37.595 s del proceso, salida 0, cero errores. Un solo
ensayo; no más consultas después. 53 consultas de preparación, 36 de medición.
No repetir ni relanzar el runner como si avanzara: usa una fuente ya consumida.

Cola añadida **89,912,198–90,037,169**, 124,972 bloques, cuatro Borrow,
una cuenta nueva. Target completo, autenticación y cohorte congelada antes
de las doce rondas. Acumulado **1,390,889 bloques contiguos**, 61 Borrow,
31 cuentas (25 con deuda en los doce hashes; seis sin deuda conservadas).

Doce bloques distintos 90,037,442–90,037,555, sin cabeceras repetidas:

- Principal, desde antes de admisión de cabecera hasta estado verificado:
  fría **4,270.030 ms**; once reutilizadas **980.560–1,130.925 ms**,
  mediana **1,051.273 ms**. Solo **2/12** cumplieron <=1 s.
- Secundaria desde despacho HTTP local: fría 4,019.207 ms; reutilizadas
  741.051–825.449 ms, mediana 807.890 ms. No confundirla con la primaria.
- Esperas de admisión acumuladas 21.978 s, incluidas en presupuesto.
- Gap mínimo de todos los inicios RPC **350.156 ms**, ninguna infracción.
- Diez intervalos entre despachos de cabecera reutilizada: 1,050.875–1,052.488 ms.
  Entre solicitudes de admisión: 981.588–1,132.486 ms, media 1,053.391 ms,
  **0.949 adquisiciones/s**. Intervalos aislados menores no violan el gate:
  dependen de cuándo terminó la respuesta anterior, no adelantan el despacho.
- Un socket cliente nuevo y 35 reutilizaciones durante observación; proxy
  existente, no prueba sobre conexión backend. No SLA ni garantía futura de cuota.
- Cobertura de borrowShares **20.6983288874%**; falta **79.3016711126%**.
  Cohorte previa en los mismos hashes: 20.6808342479%; nueva cuenta suma
  solo **0.0174946396 puntos porcentuales**, no toda la diferencia con PR15.
- Cero candidatos/cuentas calculadas como liquidables en esa cohorte y muestra.
  Cola no indexada posterior al anchor durante medición: 273–386 bloques.

Es evidencia histórica de esa captura, NO hechos actuales garantizados,
ingresos, servicio sostenido subsegundo ni ciclo de trading completo. No se
midió ruta, envío/inclusión, gas, AA/Nitro/DA o financiación. Cero candidatos
observados no descarta oportunidades en el 79.30% sin cubrir u otros bloques.

## Nueva fuente real autoritativa

`migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot/registry.json`

Raíz **`8740288f2899e8fc2056d56291ad5369f8c37d46a1e8139a5b41f3501601aaf0`**.
SHA archivo **`0346642a39cc0227bee8aa6e16f6a592d45fdb5e8ffbb29bb01a4c82aa5774d6`**.
Intervalo 88,646,281–90,037,169, estado `valid_prefix`, target completado.
Registro/cohorte auténticos, NO trazas bajo `evidence/synthetic`.
Próxima cola desde **90,037,170**, previa revalidación y anchor vigente.
No volver a fuentes PR14/PR16 y perder el avance.

## Siguiente incremento recomendado

Preparar, probar offline y publicar un protocolo NUEVO para ampliar los
**400,000 bloques inmediatamente anteriores: 88,246,281–88,646,280**.
Si un incremento posterior ya avanzó, usar su frontera más reciente.

1. Tomar la nueva raíz como fuente; conservar todas las cuentas, fuentes y
   segmentos. Selección por historia contigua, independiente de salud o
   liquidaciones conocidas. No eliminar cuentas con deuda cero.
2. Reutilizar helpers puros de unión/registro y el transporte/limitador probado,
   no ejecutar mains de PR13/PR14 con ventanas antiguas. Nuevo código/reglas/
   hashes publicados antes de RPC; no modificar protocolos registrados.
3. Un único gate de 350 ms y un único presupuesto **512 métodos/900 s TOTAL**
   para historia, validación de límites, unión, cola, autenticación y lecturas.
   Esperas incluidas; sin ráfagas acumuladas ni reset al cambiar fase/conexión.
4. Revalidar límites canónicos y checkpoint, unir sin huecos, actualizar la
   cola desde 90,037,170 a un anchor actual, congelar solo tras target completo.
   Reconciliar contra totalBorrowShares en hashes actuales. Mantener evidencia
   de prefijos y fallos entre unión y catch-up; probar esas fronteras offline.
5. No es necesario repetir la comparación de tres transportes ni la prueba
   sintética del gate. No reducir verificaciones o excluir espera para forzar
   PASS subsegundo. Mantener adquisición persistente íntegra como instrumento.
6. Si aparecen candidatos nuevos: medir supervivencia y ciclo completo
   AA/EntryPoint/bundler/paymaster/Nitro/DA, incluyendo fallos y costes, y
   patrocinio prepagado financiable. Rentabilidad/admisión siguen pendientes.

## Verificaciones efectuadas y comandos

37 pruebas aprobadas en este turno: 22 paced + 9 aislamiento antes de capturar;
6 del informe después. Un primer test nuevo tenía una clave de segmento
equivocada: se corrigió el test, quedó documentado, sin cambiar captura ni
fuentes registradas. Las 114 pruebas PR17 NO se reejecutaron completas aquí.
Auditoría offline exacta de las doce rondas y archivos persistidos aprobada.
57 fuentes y manifiestos PR13–PR17 intactos (210/175/77/38/147 archivos).
377 blobs originales, 106 workflows deshabilitados, cero activos.
Rust/Solidity no cambiaron y no se ejecutaron nuevamente.

Comando ejecutado UNA VEZ, ya terminado (no relanzar):

```bash
PYTHONPATH=/workspace/scratch/f9e56e91df85/nqc-http-deps PYTHONDONTWRITEBYTECODE=1 python migration/robinhood-paced-acquisition-20261016T1024/paced_acquisition.py --out migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot --registration-commit f82249cd9844d686b13e637b5d22a7eca88985d1
```

Reproducción SIN RED, permitida:

```bash
PYTHONPATH=/workspace/scratch/f9e56e91df85/nqc-http-deps python migration/robinhood-paced-acquisition-20261016T1024/audit_paced.py migration/robinhood-paced-acquisition-20261016T1024/evidence/pilot --out /tmp/nqc-paced-audit-check.json
python -m unittest discover -s migration/robinhood-paced-capture-20261016T1117 -p 'test_*.py' -v
```

Informe: README nuevo y `evidence/summary.json`; cuerpos/ledger/journal en
directorio pilot indicado. `evidence/provenance.json` fija hashes. El manifiesto
de este incremento cubre también pilot sin modificar el manifiesto histórico
de PR17. `verify_preflight.py` no debe reejecutarse como si no existiera captura:
su rechazo ante la presencia de pilot es intencional.

Entorno: `/workspace/scratch/f9e56e91df85/nqc-paced-capture`; Python 3.12.14,
dependencias exactas PR15 en `/workspace/scratch/f9e56e91df85/nqc-http-deps`.
Recuperar repo si desaparece. Único endpoint autorizado existente:
`https://docs-demo.robinhood-mainnet.quiknode.pro/`. Mantener TLS/proxy/no_proxy/CA,
20 s por llamada con plazo restante, límites de cuerpo/total. Sin nuevas APIs
de red. No revelar URLs privadas o credenciales; no cambiar configuración para
evadir cuotas. Toda denegación/error detiene la captura, sin reintento, proveedor
alternativo, redirección, paralelismo HTTP o sesión de rescate.

No trading, firmas, envíos, claves, gastos, suscripciones o despliegues. No tocar
nexus-engine, Cano, clientes, dominios o workflows. Evitar ejecuciones/cambios
duplicados; no crear otra tarea ni reactivar antiguas. No afirmar autorreparación
si la plataforma no invoca. Confianza alta en esta evidencia técnica, limitada
fuera de su muestra; objetivo comercial todavía pendiente.
