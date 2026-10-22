# Auditoría H9 — Protocol Adapter Registry

Fecha: 2026-10-22. Rama: `feature/sovereign-radar-omega-census-v3`.

## Alcance

H9 añade un contrato común, offline y evidence-bound para adaptadores de
protocolos. Define identidad de familia/cadena/despliegue/versión/código y una
matriz exacta de capacidades.

## Pruebas

- **20/20 pruebas H9 aprobadas**.
- `python3 -m py_compile` aprobado.
- El acumulado de suites offline H4–H9 contiene 115 pruebas aprobadas en sus
  ejecuciones auditadas; no sustituye la regresión completa.

Se probaron evidencia obligatoria por capacidad soportada, null obligatorio para
capacidades no soportadas, matriz exacta, IDs y despliegues duplicados, familias
desconocidas, Git blobs inválidos, conformance parcial, capacidades desconocidas,
determinismo, compromiso alterado y autoridades siempre en falso.

## Identidad exacta de bytes

| Archivo | SHA-256 local | Git blob publicado |
|---|---|---|
| protocol_adapters.py | `d32e66647ad4d94852db18e9fecd1581c1a33910d364efb3a916e0150457c61e` | `3435fff2021a48ad42782274b6b6601f48a34f99` |
| test_protocol_adapters.py | `1a951a6cae6a1874c960ffcb66c11dc19bf3d675987c659fef90afa2d5438083` | `b7c007404f271eb93dbf79792cf38172fb353765` |
| PROTOCOL_ADAPTER_CONTRACT.md | `9f46cc38928fd364e78c52b7efb354f83bbf89f15b6ea67cb421d91ed46f2826` | `ff0ba4d5301c740d1cf88411623011bf4cebd463` |

Los Git blobs coinciden con los archivos probados.

## Límites

La presencia de una familia en el registro no implementa el protocolo. Un
adaptador Morpho sin capacidades soportadas permanece no conformante. Este hito
no hace RPC ni certifica matemáticas, posiciones, rutas u oráculos.

## Bloqueos restantes del componente 1

1. Implementar adaptadores reales para Morpho Blue, Morpho Midnight y subastas.
2. Vincular cada capacidad a evidencia del despliegue real.
3. Ejecutar conformance cross-adapter sobre fixtures equivalentes.
4. Integrar Protocol/Fork Truth por familia.
5. Regresión completa del repositorio.

Por ello el componente 1 sigue **foundational_partial**, no certificado.
