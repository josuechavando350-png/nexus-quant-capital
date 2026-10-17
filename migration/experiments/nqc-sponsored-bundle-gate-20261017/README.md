# Directiva 004 — coordinación local y participación del financiador

Experimento del 17 de octubre de 2026. Base corregida `937a833a481fd69d2ce96152deb7d4d0760d6596`; rama propia `research/nqc-sponsored-bundle-gate-20261017`. No modifica Directiva 003. Las rutas, contratos auxiliares, mercado, oráculo y participantes son sintéticos; Morpho, Uniswap V2, Bundler3 y EthereumGeneralAdapter1 conservan sus fuentes originales fijadas.

Resultado: secuencia C1 de seis transacciones en un bloque local, comparación C1/C2 con estado idéntico y contabilidad por actor. Un bloque con transacciones independientes **no tiene rollback conjunto por revert**. La financiación y aceptación externas permanecen `BLOCKED_EXTERNAL_EVIDENCE`.

Consultar `DIRECTOR_HANDOFF.md`, `COORDINATED_BUNDLE_LOCAL.md`, `C1_C2_IDENTICAL_STATE.md`, `SPONSOR_BREAK_EVEN.md` y `VALIDATION_LOG.md`. `FINANCIER_AND_BUILDER_LEDGER.json` conserva wei enteros; `evidence/` contiene recibos, call traces y prestate diffs. El P&L NQC certificado sigue en US$0 y el potencial mensual en NO ESTIMABLE.

Los ejecutables solo arrancan un proceso hijo Anvil en loopback, sin fork, cuentas generadas ni firmas. No admiten un argumento RPC externo. No implementar un envío real a partir de este arnés.
