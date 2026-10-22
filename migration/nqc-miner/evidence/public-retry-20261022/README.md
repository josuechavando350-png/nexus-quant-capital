# Repetición pública preparada — 22 oct 2026

Estado: **PREPARADA, NO EJECUTADA**.

La configuración versionada es deliberadamente una plantilla no ejecutable:
`config.template.json` contiene `__FROM_ABOUT__` en la identidad del código y
del lock. Esto evita el problema circular de intentar guardar en el mismo commit
un archivo que pretende contener el SHA de ese commit.

Antes de cada corrida:

1. Construir un commit limpio de la rama aislada.
2. Ejecutar `nqc-miner about > /tmp/nqc-miner-about.json`.
3. Ejecutar:
   `python scripts/bind_run_config.py --template evidence/public-retry-20261022/config.template.json --about /tmp/nqc-miner-about.json --output /tmp/nqc-miner-public-retry-config.json`
4. Ejecutar `nqc-miner validate-config` sobre el archivo generado.
5. Usar un directorio de estado nuevo; nunca reutilizar el intento fallido.
6. Tras el scan, ejecutar `verify-journal` y conservar identidad del binario antes
   y después de la corrida.

Parámetros de la muestra preparada:

- run_id: `public-20261022-aave-morpho-02`
- bridge del observador: desactivado
- firma: desactivada
- presupuesto activo: 0
- tamaño de lote: 100 bloques en todos los scopes
- Cargo.lock preparado tras remediar rand 0.8.x: SHA-256
  `634f6b4361a2b29a6eeb55338422f5dbb0902fefa231433bfd385b6240a0daab`

El delta de red añade ritmo mínimo por proveedor y reintentos acotados para
respuestas transitorias (incluido 429), y falla inmediatamente ante errores HTTP
no recuperables. Los mensajes de error no incorporan URL, ruta, query string ni
cuerpo de respuesta del proveedor.

Antes de convertir esta carpeta en evidencia de integración deben ejecutarse la
compilación bloqueada, toda la suite Rust/Python, Clippy, rustfmt, aislamiento,
auditoría de dependencias, identidad del binario, `validate-config`, el scan y
`verify-journal`. Hasta entonces esta carpeta es solo un plan reproducible y
**no prueba lectura mainnet, cobertura ni rentabilidad**.
