# Continuidad después del segundo tramo anterior

Repositorio único: `josuechavando350-png/nexus-quant-capital`. Leer `AGENTS.md`.
Buscar primero PR y commits posteriores. Este incremento está en la rama
`nqc/history-continuation-20261016T0715`, sobre PR13/commit
`66f0abbf6d44c6e98a0070b2109ee375ae42de3b`. El HEAD de resultados debe verificarse
contra GitHub; no se fija anticipadamente aquí un commit todavía inexistente.

Protocolo anterior a la captura:
`5bfbad3898d1f2b97554c2485340ef5a007d8e95`, árbol
`a90fc8bc59bc606a751a1ec90b2974517db75c27`. Los 26 archivos registrados permanecen
idénticos. La captura terminó 2026-10-16 07:24:24–07:32:04 UTC, 460.83 s,
171 métodos RPC/149 HTTP/cero errores. Leer README, resumen y procedencia.

## Estado comprobado

- 1,255,917 bloques contiguos: 88,646,281–89,902,197; 127 tramos y 57 Borrow.
- 30 cuentas, 24 con deuda. Cobertura 20.2407525118%; falta 79.7592474882%.
  La cohorte previa cubre 17.2429406706% en los mismos bloques y las siete
  cuentas nuevas aportan 2.9978118413 puntos, sin atribuir cambios de mercado
  a la ampliación del índice.
- Cero señales y cero posiciones calculadas como no saludables en tres bloques.
  Margen mínimo 765/764/764 bps; regla de señal 100 bps. No prueba ausencia de
  oportunidades en cuentas omitidas ni frecuencia rentable.
- Entradas 5.350/4.602/3.351 s. Hasta estado verificado desde recibir cabecera:
  10.276/11.350/6.988 s. Incluyendo la petición inicial de cabecera:
  13.756/15.815/11.317 s. No incluye simulación de ruta, envío o inclusión.
- Auditor de interrupciones corregido en archivos nuevos; el anterior queda
  intacto. 38 puntos de fallo RPC sintético reconstruidos, además de HTTP/JSON,
  presupuestos, reorgs, fuente/tiempos alterados. Regresión exacta sobre PR13.
- 64 pruebas Python pasan; Solidity/Rust sin cambios ni nuevas ejecuciones.
  377 blobs originales preservados, 106 workflows deshabilitados, cero activos.

Fuente nueva para cualquier continuación del índice:
`migration/robinhood-history-continuation-20261016T0715/evidence/pilot/registry.json`.
Raíz SHA-256:
`3b530c3214b58b8ae4adb5dc4aa399b6e2db1994396bb2ce918302cf0a63f8de`.
No volver a la fuente de PR13 ni repetir los bloques ampliados en este ensayo.

## Próximo incremento recomendado

1. Preparar un experimento separado de transporte con conexión persistente
   frente al lector actual. Publicar código, orden de comparación, límites y
   reglas antes de medir. Usar el mismo endpoint autorizado, cohortes congeladas
   y parejas fijadas al mismo hash; comprobar igualdad exacta de resultados.
   Distinguir conexión inicial de conexiones reutilizadas y alternar el orden
   para reducir un sesgo obvio de caché. No afirmar causalidad amplia con pocos
   pares ni atribuir diferencias a una causa no aislada.
2. Respetar proxy/configuración de red, límites de bytes y timeout; sin reintentos,
   redirecciones, paralelismo de HTTP o cambio de endpoint tras rechazo. Una
   conexión persistente no autoriza continuar después de una denegación. Verificar
   en documentación primaria las APIs del transporte que se elija y probarlo
   offline, incluidos fallos, antes de usarlo con estado real.
3. Actualizar únicamente la cola del registro actual y congelar la cohorte antes
   del benchmark si necesita estado vigente. No repetir un escaneo anterior por
   reutilizar un comando que fija otra ventana. Medir tanto entradas como estado
   verificado, y conservar los huecos entre checkpoint y observación.
4. Para ampliar después el pasado, el siguiente intervalo contiguo de 400,000
   bloques es **88,246,281–88,646,280**, unido a la fuente actual y seguido de
   catch-up. Publicar una política nueva; no cambiar las políticas históricas.
   Si hay una iteración posterior, usar su frontera en lugar de este intervalo.
5. Si aparecen candidatos nuevos bajo reglas previas, registrar y medir su
   supervivencia y el ciclo AA/Nitro/DA. Una señal o deuda no es beneficio.
   Bundler y patrocinio financiado siguen pendientes de admisión y condiciones
   comerciales verificables; no hay financiación comprometida.

Cada ejecución debe cerrar un incremento acotado con evidencia, pruebas y PR
borrador. Máximo 512 métodos RPC/900 s de captura por ejecución, no por sublote.
No evadir cuotas ni borrar resultados negativos. Conservar prefijos parciales.
Evitar capturas o cambios duplicados revisando PR/ramas recientes. Si falta una
capacidad, informar el bloqueo exacto y completar lo que sea posible offline.

## Reproducción y herramientas

```bash
python -m unittest discover -s migration/robinhood-history-continuation-20261016T0715 -p 'test_continuation.py' -v
python migration/robinhood-history-continuation-20261016T0715/audit_continuation.py migration/robinhood-history-continuation-20261016T0715/evidence/pilot --out /tmp/nqc-audit.json
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

Se usó un worktree separado. GitHub permitió crear árbol, commit, rama y PR;
`git fetch` permitió verificar y alinear el árbol local con el remoto. No se
usó push autenticado por CLI. Recuperar desde GitHub si el entorno desaparece.
El Python del recolector usa biblioteca estándar y el bytecode ya comprobado.
No requiere toolchain Solidity para volver a auditar las respuestas guardadas.

Sin firmas reales, transacciones, gastos, despliegue, nuevas suscripciones,
secretos, merge automático o workflows habilitados. No tocar nexus-engine,
Cano, clientes ni dominios. Mantener el objetivo comercial visible y comunicar
confianza y límites; no prometer autorreparación cuando no se haya observado
una ejecución o un fallo concreto. El trabajo sigue pendiente; no desactivar
su continuidad por haber terminado únicamente este lote.
