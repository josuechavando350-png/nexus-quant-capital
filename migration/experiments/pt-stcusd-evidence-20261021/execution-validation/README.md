# NQC PT-stcUSD — validación ejecutada y bloqueos conservados

Rama autorizada: `research/pt-stcusd-evidence-20261021`.
HEAD remoto inicial: `ef42fa89eb990817892f468ed038b37ed5a21821`.
Se añaden archivos únicamente dentro de esta carpeta; `route-audit/` y el resto del historial no se alteran.
Empezar por `RESULTADO_FINAL.md`. Los documentos de replay señalan explícitamente lo no ejecutado.

## Reproducir sin red ni secretos

Desde esta carpeta:

```sh
python3 -B -m unittest discover -v -s tests
python3 -B src/economic_audit.py
python3 -B src/preflight.py --capture evidence/alchemy
```

El último comando debe terminar con código **2**, porque faltan los inputs reales. No es un PASS.
Desde la raíz del repositorio:

```sh
python3 -B -m unittest discover -v -s migration/experiments/pt-stcusd-evidence-20261021/route-audit/tests
python3 -B migration/verify_isolation.py
python3 -B -m unittest discover -v -s migration -p test_isolation.py
```

`input/` preserva los tres archivos del ZIP adjunto; sus ocho pruebas usan mocks y solo prueban el sondeo.
`evidence/test_commands.json` registra comandos y exit codes. `SHA256SUMS` cubre el contenido entregado
salvo el propio manifiesto; `evidence/provenance.json` registra origen y HEAD inicial.

## Adquisición posterior autorizada

Con `NQC_RPC_URL` ya configurado como secreto en el entorno, sin imprimirlo:

```sh
python3 -B src/acquire.py --source alchemy --output /ruta/nueva/nqc_capture
python3 -B src/preflight.py --capture /ruta/nueva/nqc_capture
```

Usar un directorio nuevo: las capturas existentes no se sobrescriben. El colector está limitado a
nueve lecturas RPC lógicas (hasta tres reintentos por HTTP 5xx): chainId, dos cabeceras, transacción, receipt, código Morpho al padre y tres trazas
(prestate, callTracer, diff). Se detiene ante cadena no verificada o rechazo HTTP 401/403/429.
Es un primer paquete de recuperación, no la adquisición completa de todas las pruebas de cuentas/slots
ni una certificación del estado. El código no contiene métodos de firma/envío ni claves.
Los mensajes de error se conservan con endpoint/credencial redactados; revisar además cualquier captura
externa antes de publicarla. No reutilizar la sesión Blockscout rechazada de esta investigación.

Los archivos de bloques son respuestas de indexador, no cabeceras RPC ni pruebas de consenso.
Los datos de contratos no autentican implementaciones históricas. La disponibilidad de Foundry no
subsana inputs ausentes. Las versiones y hashes de herramientas están en `evidence/toolchain*.json`
y `evidence/new_tool_versions.json`; los binarios permanecen fuera del repositorio.
