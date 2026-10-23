# Auditoría: condiciones iniciales e importes Aave

Fecha de entrega: 22 de octubre de 2026, America/Mexico_City.
Avance global: **43/100**; ninguna fase operativa adicional cerrada.

## Resultado

Se recuperó la entrega local de condiciones iniciales pendiente de publicación.
Antes de extenderla se comprobaron todos los hashes de fuentes y logs de su
resumen, además de la integridad de su bundle. Conserva sus 96 registros de
solo lectura y el resultado original: un estado pasa condiciones iniciales y
dos rechazan por salud. No hubo nuevas consultas de red ni eventos en esta
continuación. Se preservaron también los intentos fallidos de compilación y
trazas de esa entrega, sin reinterpretarlos como éxitos.

Se añadió `calculate-aave-amounts`, un núcleo Rust sin red para factor de cierre,
importes máximos, disponibilidad de colateral, bonus, comisión y polvo. Reproduce
los redondeos y reversiones de los helpers de la fuente retenida. La referencia
Solidity contiene el segmento aritmético original extraído byte por byte y llama
a la función interna de colateral importada sin modificaciones. Los archivos
originales no se alteran. Se conserva una compilación real con solc 0.8.27 de
hash fijado, sus entradas/salidas y el fixture ejecutado en REVM.

## Verificación de la entrega

- **177 pruebas Rust** y **267 pruebas Python** aprobadas, sin fallos ni omitidas.
- El conjunto diferencial de importes compara **2205 casos** completos; otra
  prueba añade un caso de colateral agotado con redondeos de deuda y comisión:
  **2206 ejecuciones sintéticas** contrastadas en total. Son casos dentro de las
  pruebas anteriores, no 2206 pruebas generales adicionales.
- El conjunto principal produjo 1688 éxitos y 517 reversiones: 212 vacías de
  helpers, 300 pánicos de aritmética, una división por cero y cuatro por polvo.
  Se compararon seis cantidades o todos los bytes de reversión; no solo éxito.
- La batería conserva las comprobaciones previas de condiciones iniciales:
  539 casos sintéticos y tres entradas históricas en el adaptador sintético.
- Clippy con advertencias como errores, formato, identidad del binario y
  aislamiento aprobados. El binario coincide con las fuentes auditadas y marca
  `source_dirty=false` para `ac41b44d5c1abb603dcd185308618924e030b752`.
- El aislamiento conserva 531 archivos originales, 106 workflows deshabilitados
  y cero activos. El diff de esta entrega se limita a `migration/nqc-miner/`.
- `verification.json` fija hashes de los archivos de evidencia; `offline/`
  conserva las salidas completas. `source-history.bundle` permite recuperar el
  commit auditado, partiendo de `5e88d25`, incluido en el bundle de condiciones.

El primer conjunto de importes pasó cuatro pruebas; después se agregó el caso
explícito de agotamiento y la batería final pasó las cinco. No se oculta un fallo
entre ambos: la ampliación solo añade cobertura.

## Alcance real

La aritmética recibe balances, índices ya aplicados, precios, salud, deuda total
y bonus elegido por el llamador. No autentica esos valores ni demuestra cómo
se obtuvieron. El resultado no ejecuta las condiciones iniciales ni los pasos
posteriores sobre tokens. Una entrada saludable puede pasar la aritmética;
esto se prueba para impedir que se interprete como permiso de liquidación.

No se ha reproducido una liquidación completa ni el estado justo anterior a una
transacción. Faltan índices y saldos escalados, eMode, déficit, liquidez,
transferencias, dependencias autenticadas, fork histórico real, integración
operativa y economía. La comisión calculada precede al ajuste final por saldo
escalado. Cancun es el entorno del harness sintético, no una certificación del
fork de los bloques históricos. No se ejecutó Foundry fuzzing ni una compilación
hermética; las pruebas con semilla fija no se presentan como sustitutos.

Observer no cambia; no se habilita despliegue, firma, transacción ni gasto.
