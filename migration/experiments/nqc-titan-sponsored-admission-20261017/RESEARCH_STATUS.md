# Continuidad — NQC Directiva 005, 2026-10-17

Rama: `research/nqc-titan-sponsored-admission-20261017`. Base004: `9988e425bdd8e5e9a9db7666cd9e8122404c39e0`. Commit actual: `git rev-parse HEAD`; publicación/read-back en PUBLICATION.md (evita hash autorreferente).

Implementado: manifiestos I/II unsigned, gate EVM/identidad/política con PASS_LOCAL/REFUTED/UNKNOWN, ledger exacto por actor, tres variantes EVM nuevas y una frontera con reserva por prefijo. Rutas oficiales Morpho/Uniswap y ejecutor sin cambios. C2 y B permanecen pendientes en su alcance previo.

Ejecutado: 3 variantes nuevas / 11 recibos de candidato (5+5+1); 12 pruebas nuevas PASS, 14 pruebas de evidencia 004 PASS, 9 aislamiento PASS y verificador PASS limitado. Se excluyen del recuento los recibos de setup y simulaciones descartadas para fijar U. Se conciliaron offline 26 escenarios anteriores. Cero fallos inesperados pendientes. V05 pérdida y V07 inclusión incompleta son resultados negativos esperados, no tests fallidos. No se recompiló ni reejecutó la suite Solidity/168 Python/Rust o los 27 escenarios EVM completos.

Resultados: V05 builder −0.004636412 ETH; V06 +0.045363588 ETH, NQC +0.159365645570551238 WETH, ambos sólo sintéticos. V07 builder −0.000052 ETH, U=0. Se refuta que éxito de liquidación o refund a otro actor pruebe beneficio builder. Coinbase queda separado. Eliminar pago interno realmente ejecutando cinco tx ahorra 21,000 gas.

Límites: identidades/financiación de fixture; cuenta builder inicial 100 ETH sintéticos; pool override no prueba trigger de Titan. Sin firmas, contactos, relay, operación pública, gasto ni servicios persistentes. Destinatarios comerciales y no recurso null. Documentación web legible; descarga directa .md de ambas fuentes devolvió HTTP403, sin reintentos. No hay cuerpo raw autenticado de esas páginas; se guardan URL, corte, sección y extracto mínimo.

B: BLOCKED_PRESTATE, sin nuevo testigo padre+tx0+Fluid. No nuevo censo. No aceptación real ni beneficios NQC. Mensual NO ESTIMABLE. Requisitos para objetivos monetarios siguen sin evidencia de frecuencia/margen/captura admisible; no se estiman aquí.

Próximo objetivo: expediente público autenticado de V06 que cierre identidad, anticipo/prefijos/devolución, ingreso neto exigido y S1–S12 sin recurso personal. Archivos: C1_BUNDLE_INTENT.json, BUILDER_SPONSORSHIP_SPEC.md, ADMISSION_AND_NO_RECOURSE_GAPS.md. Criterio: campos cubiertos por fuente aplicable, no placeholders; todavía distinto de aceptación real. PAUSAR si exige contacto, firmas, pago o datos privados.

Reproducción y herramientas en README.md; fuentes/hashes en SOURCE_LOCK.json y MANIFEST.sha256; resultados y comandos en evidence/. Sólo esta carpeta nueva cambia respecto de 004.
