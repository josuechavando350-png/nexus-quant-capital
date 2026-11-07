# SUPERHUNTER — Slither: tres controles obligatorios (PR sucesor de #72)

**Tecnología externa:** Slither #6 (crytic/slither), versión prevista 0.11.6.
**Estado real:** código del adaptador en laboratorio; no se ha ejecutado el analizador real ni `solc` en esta entrega, ni la QA integral. **No** hay nuevas vulnerabilidades confirmadas.
**Rama:** `feat/superhunter-slither-adversarial-negative-20261107`.

## Razón técnica

El PR #71 incluía un caso positivo que usa `require(tx.origin == owner, "owner")`. El PR #72 añadió un negativo sencillo en el que `tx.origin` se sustituye por `msg.sender`. Sin embargo, eso no comprueba si el detector diferencia un *uso especial* de `tx.origin` de un uso inseguro como autorización.

El detector real de Slither 0.11.6 (`slither/detectors/statements/tx_origin.py`) busca referencias a `tx.origin` en nodos condicionales y **las excluye si el nodo también lee `msg.sender`**. Es una decisión de ese detector; no certifica que cualquier contrato con ese patrón sea seguro.

Por eso incorporamos un tercero. Los tres contratos son fuentes fijas derivadas del mismo fixture de propiedad del proyecto, jamás desplegadas:

| Control | Condición Solidity | Resultado esperado `tx-origin` | SHA-256 del fuente |
|---|---|---|---|
| Positivo | `require(tx.origin == owner, "owner")` | Exactamente **1** alerta ligada a fuente | `ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64` |
| Negativo simple | `require(msg.sender == owner, "owner")` | **0** alertas | `f4435d614ec0d890f56f06c6250bba4a60152255fa3f8d5ceec13952f9aba0f1` |
| Negativo adversarial específico | `require(tx.origin == msg.sender, "direct caller")` | **0** alertas | `45e77d6d43ee7a13720323e48ed103e64447013c705af58f53e824ae3807df92` |

## Qué se programó

- `slither_owned_worker.py`: modo opcional literal `comparison` con SHA exacto del tercer contrato. El worker no acepta Solidity, URLs, direcciones ni comandos arbitrarios.
- `slither_control_pair.py`: el comando heredado `run-owned-slither-pair` ejecuta **tres** subcontroles; el nombre del CLI se conserva por compatibilidad. El tercer modo usa la misma versión fija y compilador comprobado y produce su propio subexpediente `comparison/`.
- El verificador final exige `positive/`, `clean/` y `comparison/`, revalida los tres recibos del importador, sus hashes, los tres source digests, el scope y **un solo commit declarado**. Un reporte positivo ausente, un falso positivo de cualquiera de los negativos, un booleano disfrazado de contador, un informe mixto o un subexpediente faltante provoca rechazo.
- El manifiesto `COMPLETE.json` conjunto se escribe **al final**; queda ausente si cualquier control falla. Su hash es solo consistencia de bytes, no una firma ni una prueba de que el scanner se ejecutó.
- Las regresiones del tercer control se añadieron a `test_slither_control_pair.py` y a la lista de tests obligatorios de `quality.py`. El selector de QA completo debe probarlas en su entorno fijado antes de promover.

## Contrato operativo

En un laboratorio Linux aislado, con Slither 0.11.6, crytic-compile 0.4.2 y `solc` oficial 0.8.30 con SHA fijado (solo tras verificación de supply-chain), el CLI **conserva los nombres existentes**:

```sh
python3 -m superhunter run-owned-slither-pair \
  --solc /privado/solc-fijado --repo-commit SHA40 \
  --out /privado/tres-controles-nuevo
python3 -m superhunter verify-owned-slither-pair \
  --bundle /privado/tres-controles-nuevo
```

No copiar los ejemplos literalmente sin disponer del binario fijado, del sandbox sin egress y de las autorizaciones pertinentes. La integración **no crea un sandbox de red**; únicamente hereda la limitación y limpieza de procesos local. Tampoco autentica al operador que declara `repo-commit` ni realiza replay independiente del scanner.

## Estado y próximos gates

1. **Hecho en código:** tercer modo con SHA, generación de tres expedientes, contraste de positivos/negativos, binding del commit y regresiones.
2. **Pendiente:** ejecutar las nuevas pruebas con el checkout real y QA completa, sin saltos ni pérdidas de pruebas históricas. Cualquier ejecución local sintética debe etiquetarse como tal.
3. **Pendiente:** descargar y auditar las dependencias en host habilitado, comprobar versiones y SHA, ejecutar los tres casos con Slither real y verificar que los recuentos esperados coinciden; repetir con entorno independiente.
4. **Pendiente:** medir latencia, tasa de falsos positivos en un corpus más amplio y costo. Tres casos conocidos **no** miden generalización, tasa de descubrimientos originales ni competencia mundial.

**Para futuras IAs:** no fusionar automáticamente la cadena de PRs; leer `AGENTS.md`, `SUPERHUNTER_STATUS.md`, `REPOSITORIES_50.md`, `SLITHER_OWNED_LAB.md`, `SLITHER_PAIR_GATE.md` y esta guía. No asignar un progreso de 1/50 certificado por una prueba sintética o un gate documental.
