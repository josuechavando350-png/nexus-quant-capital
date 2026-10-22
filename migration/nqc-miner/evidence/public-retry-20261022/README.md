# Repetición pública preparada — 22 oct 2026

Estado: **PREPARADA, NO EJECUTADA**.

Esta ejecución conserva intacto el intento anterior y usa una identidad nueva:

- run_id: `public-20261022-aave-morpho-02`
- código a construir: `20a22c58b7bc64c6cda6d9610133b876452de0fe`
- Cargo.lock SHA-256: `c840affc2bcf9f55429d92e20a5d46dc309d9fc606b738669ab2a709b087c80a`
- bridge del observador: desactivado
- firma: desactivada
- presupuesto activo: 0
- tamaño de lote: 100 bloques en todos los scopes de esta muestra

El delta de red añade ritmo mínimo por proveedor y reintentos acotados para
respuestas transitorias (incluido 429), y falla inmediatamente ante errores HTTP
no recuperables. Los mensajes de error no incorporan URL, ruta, query string ni
cuerpo de respuesta del proveedor.

Antes de convertir esta carpeta en evidencia de integración deben ejecutarse,
sobre el commit indicado, la compilación bloqueada, toda la suite Rust/Python,
Clippy, rustfmt, aislamiento, identidad del binario, `validate-config`, el scan
con un directorio nuevo y `verify-journal`. Hasta entonces esta carpeta es solo
un plan reproducible y **no prueba lectura mainnet, cobertura ni rentabilidad**.
