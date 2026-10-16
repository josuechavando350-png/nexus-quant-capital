# Relevo: transporte persistente comprobado, adquisición completa pendiente

Repositorio único autorizado: `josuechavando350-png/nexus-quant-capital`.
Buscar PR/commits posteriores primero; leer AGENTS.md, este archivo y README.
Rama de resultados: `nqc/transport-benchmark-20261016T0821`, apilada sobre PR14
`26bf4105926a57480a0a920091d8dc3f720351a4`. Verificar HEAD publicado en GitHub;
no fijar aquí un commit de resultados que aún no existía al escribir el archivo.

Protocolo publicado antes de medir:
`8bdd6f8be2cc16ceb6c8330d9186c60cde90c522`, árbol
`bae5302735d65daab17ade950e186edc70161a74`.
Captura **terminada**, 16/oct/2026 08:38:26–08:40:21 UTC, 49 métodos/49 HTTP,
114.687 s de journal, 208,663 bytes de cuerpos y cero errores. No reejecutarla
como si avanzara un protocolo de otro ensayo. No modificar sus fuentes registradas.

## Qué sí está demostrado en esta muestra

- Seis bloques, tres modos por bloque, igualdad exacta ABI/estado derivado.
- Conexión persistente inicial: entradas 2,823 ms; verificado 2,956 ms.
- Cinco lecturas reutilizadas: entradas 72–316 ms (mediana 82); estado verificado
  214–424 ms (mediana 234). Mismo socket cliente en las 11 peticiones posteriores
  a la primera, por el proxy configurado; no prueba la conexión backend del nodo.
- Control urllib: entradas 2,391–3,095 ms; verificado 5,033–6,998 ms.
  Control Requests nuevo por petición: entradas 2,495–8,662 ms; verificado
  5,179–13,209 ms. Se conservaron todos los valores y el arranque frío.
- La petición inicial de cabecera siguió siendo urllib. Desde pedirla hasta estado
  persistente verificado: 2.723–26.398 s, con esperas por orden y autenticación.
  **No está demostrado el objetivo completo de 1 s**, ni ruta/envío/inclusión.
- 30 cuentas/24 con deuda; cobertura nueva 20.2405733935%, faltante 79.7594266065%.
  Cero candidatos en los seis bloques. Nada de esto acredita beneficio realizado.
- 80 pruebas Python, incluidas 16 nuevas; 49 fronteras RPC sintéticas interrumpidas.
  Replay offline de captura real, manifiestos PR13/14 intactos; 377 blobs originales,
  106 workflows deshabilitados, cero activos. Rust/Solidity sin cambios ni ejecución.

## Próximo incremento acotado

1. Prerregistrar adquisición completa persistente: pedir cabecera, lectura única
   fijada por hash y comprobación canónica en la misma sesión. Medir desde antes
   de solicitar cabecera hasta estado verificado; distinguir frío/reutilizado.
   No repetir la comparación de tres modos ya completada. No prometer subsegundo.
2. Si se mide estado vigente con cohorte actualizada, extender **solo la cola**
   de la fuente PR14 antes de congelar; no repetir escaneos pasados. Conservar
   cuentas con cero deuda. Revalidar límites, unir sin huecos, reconciliar shares
   en cada hash observado y declarar historia/tail faltantes. Selección independiente
   de salud y liquidaciones conocidas. Código/política/hashes publicados antes de RPC.
3. Reutilizar lector persistente bajo las mismas restricciones, no integrarlo
   silenciosamente en protocolos anteriores. Probar offline herencia de presupuestos,
   límites y paradas en el runner nuevo; no reintentar sobre otra sesión tras error.
4. Ampliación posterior aún pendiente: 400,000 bloques **88,246,281–88,646,280**.
   Este ensayo no agregó historia ni cola. Si otro incremento ya avanzó, usar su
   fuente más nueva. No derivar un índice nuevo de `source-registry.json` sin
   mantener su procedencia y hash originales.
5. Candidatos nuevos: supervivencia, simulación completa AA/EntryPoint/bundler/
   paymaster/Nitro/DA, costes de fallos y financiación prepagada. Admisión comercial,
   captura repetible y margen neto positivo siguen pendientes, no como tareas terminadas.

## Fuente del índice (sin cambios)

`migration/robinhood-history-continuation-20261016T0715/evidence/pilot/registry.json`

Raíz: `3b530c3214b58b8ae4adb5dc4aa399b6e2db1994396bb2ce918302cf0a63f8de`.
SHA del archivo: `19034043d9e0b56919018ebfc8a3bc50787873d6c8f146593606df3ec2daf47a`.
Intervalo 88,646,281–89,902,197; 1,255,917 bloques/57 Borrow. En las observaciones
de este ensayo hubo 40,320–41,209 bloques posteriores fuera del índice.

## Comandos y entorno

```bash
python -m unittest discover -s migration/robinhood-transport-benchmark-20261016T0821 -p 'test_*.py' -v
python migration/robinhood-transport-benchmark-20261016T0821/audit_transport.py migration/robinhood-transport-benchmark-20261016T0821/evidence/pilot --out /tmp/nqc-transport-audit.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Python 3.12; dependencias exactas en requirements.txt. En este entorno se instalaron
sin suscripción/gasto en `/workspace/scratch/f9e56e91df85/nqc-http-deps`; añadir ese
directorio a PYTHONPATH si todavía existe. Worktree separado en
`/workspace/scratch/f9e56e91df85/nqc-transport-review`. Recuperar de GitHub si falta.
No cambiar proxies/CA ni volcar URLs/secretos. APIs verificadas en fuentes primarias
en PRE_REGISTER y mediante pruebas locales; el lector usa solo el endpoint ya autorizado.

Captura ejecutada una sola vez:
`benchmark.py --out migration/robinhood-transport-benchmark-20261016T0821/evidence/pilot --registration-commit 8bdd6f8be2cc16ceb6c8330d9186c60cde90c522`.
GitHub permitió publicar árbol/commit/ramas; fetch verificó árbol exacto. No se
requiere push CLI autenticado. Mantener PR borrador, sin fusionar.

Techo por ejecución: 512 métodos RPC/900 s TOTAL. No reintentos/redirecciones/
paralelismo HTTP/cambio de proveedor tras denegación. Conservar negativos/prefijos.
Sin trading real, firmas, envíos, claves, gastos, suscripciones o despliegues.
No tocar nexus-engine, Cano, clientes, dominios ni workflows. Evitar ejecuciones
duplicadas. El objetivo comercial no ha terminado; no detener continuidad solo
porque este ensayo completó sus mediciones. No prometer autorreparación o actividad
futura cuando no se observe una ejecución concreta.
