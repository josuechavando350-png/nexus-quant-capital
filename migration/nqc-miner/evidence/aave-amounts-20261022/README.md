# Evidencia del núcleo de importes

- `compiler/`: entrada/salida exacta de la compilación real del harness extraído;
  fuentes originales intactas y compilador fijado por SHA-256.
- `targeted-initial.txt`: primer pase de cuatro pruebas Rust; incluye desglose
  de los 2205 casos diferenciales. La batería final añade una quinta prueba y
  otro caso Solidity de agotamiento de colateral.
- `offline/`: 177 Rust, 267 Python, Clippy, formato, identidad e aislamiento.
- `source-history.bundle`: commit auditado `ac41b44`, requiere `5e88d25` del
  bundle preservado en `../aave-conditions-20261023/source-history.bundle`.
- `verification.json`: resumen y hashes exactos de entrega.

Consultar `docs/AUDIT_AAVE_AMOUNTS_20261022.md` y
`docs/aave-liquidation-amounts.md` para el significado y límites. Se trata de un
núcleo aritmético sintético después de validación/actualización de índices,
antes de transferencias. No es un replay completo ni prueba de rentabilidad.
No agrega observaciones históricas. Avance global: 43/100.
