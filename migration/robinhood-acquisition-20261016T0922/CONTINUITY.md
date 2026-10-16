# Relevo después de HTTP 429: preservar prefijo, limitar ritmo antes de medir

Repositorio único: `josuechavando350-png/nexus-quant-capital`. Buscar primero PR y
commits posteriores, leer AGENTS.md y README. Rama `nqc/acquisition-20261016T0922`,
sobre PR15 `170148bf07920ae0e9112cc7f28507ca6051dd77`. Verificar HEAD remoto;
no anticipar aquí un hash de resultados que todavía no existía al redactar.

Protocolo previo: `d03ecc8e1106488e80d33d8a4beecff65375db80`, árbol
`28dc9e433543f26c0159748698d66361ed3a512b`. Sus 46 fuentes permanecen intactas.
Captura **detenida**, 16/oct/2026 09:32:09.516–09:32:14.639 UTC, 5.123 s,
10 métodos/10 HTTP, un error. Salida de proceso 1. No hubo reintento ni failover.

## Hecho nuevo decisivo

Petición 10, `eth_getLogs` 89,912,198–89,922,197: **HTTP 429**, cuerpo
`{"code":-32007,"message":"5/second request limit reached"}`.
Ocho inicios de petición en unos 912 ms según reloj local. Límite declarado en
esa respuesta, no SLA ni prueba del alcance exacto/compartido de la cuota.
El transporte rápido permite exceder la tasa del demo; no basta con reducir latencia.

Solo se validó el primer tramo nuevo 89,902,198–89,912,197: 10,000 bloques,
cero Borrow/cuentas nuevas. Prefijo acumulado 88,646,281–89,912,197,
**1,265,917 bloques, 57 Borrow y 30 cuentas conservadas**. El objetivo elegido
era 89,973,963: quedaron 61,766 bloques hasta ese objetivo histórico, y la cola
actual deberá recalcularse con un protocolo nuevo.

No se congeló cohorte, no se autenticó aún el objetivo completo, no ocurrió la
rotación de medición y hubo **0/12 adquisiciones**. No se midieron cobertura vigente,
deudores, candidatos, latencia completa, rutas, gas o rentabilidad. No convertir
ausencia de observación en cero candidatos. Las cifras PR15 siguen históricas.

92 pruebas Python: 12 nuevas y 80 regresiones; 59 fronteras RPC sintéticas con
fallos auditados, límites compartidos antes/después de rotación, reorgs y tampering.
Replay real detenido conserva archivos y segmentos exactamente. 377 blobs
originales, 106 workflows deshabilitados, cero activos. Rust/Solidity sin cambios
ni nuevas ejecuciones. Confianza alta en parada/prefijo, no en monetización.

## Fuente más reciente, aunque parcial

`migration/robinhood-acquisition-20261016T0922/evidence/pilot/registry.json`

Raíz `c57a798823c6163a54588353b92269fd98cd050cc96c9afb6123741d6752f7de`.
SHA del archivo `67d8a5c619bf025e410e785838e9f08b5919a6e844112eb22911b17369c501ee`.
Checkpoint 89,912,197, estado `valid_prefix`. No equivale a target completo o a
cohorte congelada. Revalidar límites antes de continuar; mantener fuente anterior
y evidencia. **No repetir los 10,000 bloques confirmados volviendo a PR14.**

## Próximo incremento

1. No más RPC en esta ejecución ni reejecución de este protocolo para reemplazar
   el rechazo. La limitación es transitoria: no desactivar la continuidad por ello.
2. Preparar y publicar NUEVA política/código/hashes con un limitador global de
   frecuencia para toda petición, incluida preparación y observación. Propuesta
   conservadora: separación mínima 350 ms entre inicios, sin ráfagas acumuladas,
   sin paralelismo, sin reintentos y conservando 512 métodos/900 s TOTAL.
3. Probar el limitador offline con reloj inyectado: separación real, no reset al
   rotar conexión, esperas dentro del presupuesto, nada después de error, negativos
   preservados, cero eliminación de rondas lentas. No modificar fuentes registradas.
4. **Incluir espera de admisión anterior a la cabecera** en la latencia completa;
   separar ese dato del tiempo desde iniciar HTTP y reportar cadencia sostenida.
   Con tres solicitudes y 350 ms de separación, la cadencia mínima es ~1.05 s:
   no forzar un PASS subsegundo excluyendo esperas. Confirmar lo observado, no prometerlo.
5. En una futura ejecución acotada, bajo esa política publicada y sin saltar la
   cuota, continuar solo cola desde 89,912,198; recalcular anchor vigente. Congelar
   todos los prestatarios tras target completo/autenticación. Medir cabecera +
   lens + canonical check persistentes; frío separado de reutilizado. Cualquier
   nuevo 429/denegación/timeout/error detiene todo, sin endpoint o sesión de rescate.
6. Historia anterior pendiente sin cambios: 88,246,281–88,646,280. Hacerla después
   con otra política; si una iteración posterior avanzó usar su frontera.
7. Nuevos candidatos: supervivencia y ciclo AA/EntryPoint/bundler/paymaster/Nitro/DA,
   costes incluidos fallos y financiación prepagada. Captura repetible, margen y
   condiciones comerciales siguen pendientes; no hay fondos comprometidos.

## Entorno y reproducción

Worktree `/workspace/scratch/f9e56e91df85/nqc-acquisition-review`; dependencias
PR15 `/workspace/scratch/f9e56e91df85/nqc-http-deps` en PYTHONPATH si persisten.
Python 3.12, versiones exactas en requirements.txt de PR15. Recuperar de GitHub
si desaparecen. Único endpoint existente `https://docs-demo.robinhood-mainnet.quiknode.pro/`.
No cambiar proxy/no_proxy/CA ni extraer credenciales. Las APIs de transporte son
las mismas fijadas y probadas en PR15; no hubo nueva biblioteca de red.

```bash
python -m unittest discover -s migration/robinhood-acquisition-20261016T0922 -p 'test_*.py' -v
python migration/robinhood-acquisition-20261016T0922/audit_acquisition.py migration/robinhood-acquisition-20261016T0922/evidence/pilot --out /tmp/nqc-acquisition-audit.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Captura única ejecutada: `acquisition.py --out migration/robinhood-acquisition-20261016T0922/evidence/pilot --registration-commit d03ecc8e1106488e80d33d8a4beecff65375db80`.
GitHub permite publicar árbol/commit/ramas y PR borrador; fetch verifica árbol
exacto. No merge. Mantener cada ejecución acotada y evitar cambios duplicados.
No tocar nexus-engine, Cano, clientes, dominios, despliegues o workflows.
Sin trading, firmas, envíos, claves, gastos, suscripciones o evasión de cuotas.
No afirmar que el programador se autorrepara si la plataforma no invoca la tarea.
