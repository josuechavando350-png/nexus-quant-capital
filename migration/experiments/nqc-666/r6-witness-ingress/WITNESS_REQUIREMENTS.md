# Testigo que falta para cerrar la integración auténtica

No se pide repetir rentabilidad, financiación o auditoría. Hace falta un paquete
técnico de estado verificable para el ámbito que R5 ya soporta:

| Elemento | Condición |
|---|---|
| Cadena y punto de estado | Ethereum, chainId 1, estado al final de un bloque identificado por hash |
| Encabezado | Todos los campos Pectra requeridos por R3/R5; hash RLP/Keccak coincidente; procedencia conservada |
| Anclaje | Evidencia independiente que permita confiar en ese hash de bloque; una respuesta RPC/requireCanonical o etiqueta no es consenso |
| Cuenta Morpho | Dirección fijada por política, prueba desde stateRoot, nonce/balance/storageRoot/codeHash consistentes |
| Runtime | Bytes completos cuyo Keccak coincide con codeHash; la atestación de layout de ese runtime sigue siendo una condición aparte |
| Posición/mercado | marketId, borrower y 9 slots exactos derivados por R3.slots: posición, supply, borrow, time_fee y 5 parámetros |
| Storage | Prueba de pertenencia o ausencia de cada slot desde storageRoot; no rellenar ausencias de captura con cero |
| Captura | Las cuatro respuestas crudas y sus solicitudes fijadas al mismo hash; conservar bytes, errores y procedencia |
| Política independiente | Anchor, address, code_hash, market_id, borrower, max_age_s y layout; no derivarla de un paquete no confiable y llamarla autenticada |

`scripts/import_capture.py --policy ... --out ...` genera las solicitudes exactas
con los slots calculados, pero no las envía. El importador consume una captura
local y conserva los archivos originales. La verificación de pruebas vincula
cuenta/storage a la raíz fijada; no resuelve automáticamente el anclaje de cadena.

Para el frente NQC031 de cadena 4663, tx índice 1, esta interfaz **no corresponde**:
requiere su raíz intermedia/contexto Nitro autenticados. No se cambia chainId ni
se sustituye ese preestado por el bloque padre o por el estado final. Esa tarea
permanece separada. El artefacto recibido declara 0 pruebas verificadas, 11
lecturas desconocidas y raíz pretransacción null; sus bytes se conservan como
evidencia del bloqueo, no como valores de mercado certificados.

Aunque llegue el testigo Ethereum, siguen pendientes vigencia/ejecución de oráculo,
acumulación real de intereses/IRM cuando corresponda, simulación del candidato,
gas/inclusión y autorización financiera/no recurso. R6 no convierte un escenario
con precio supuesto en observación ni abre la puerta comercial.
