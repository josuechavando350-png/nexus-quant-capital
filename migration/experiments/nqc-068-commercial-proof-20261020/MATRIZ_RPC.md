# Matriz de disponibilidad histórica

Caso Ethereum 21762897, índice 1. Respuestas conservadas; detalles por llamada en EVIDENCIA_CANONICA.json.

| Dato | Estado | Alcance |
|---|---|---|
| Recibo objetivo | Disponible | 11 logs; 602029 gas; status 1; sin prueba de inclusión de recibo |
| Recibo tx0 | Disponible | 76 logs; 1624673 gas; status 1; no reproduce tx0 |
| Cuerpos tx0 y tx1 | Verificados por hash | RLP firmado histórico y recuperación del firmante; cero firmas nuevas |
| Bloques padre/objetivo | Hashes recomputados | RLP de cabeceras coincide; consenso independiente no comprobado |
| Bloque completo objetivo | 41 transacciones verificadas | Raíz transactionsRoot recomputada e idéntica |
| Código al padre | Parcial | 9 respuestas de cuentas; dos son 0x legítimos de EOA/precompilado |
| Saldo ETH al padre | Parcial | 9 respuestas; no cubren todos los participantes |
| Nonce al padre | Parcial | 8 respuestas |
| Storage al padre | Parcial | 12 respuestas; primera ausencia exacta: router slot 0x3 |
| Preestado inmediato tx1 | No disponible | tx0 no terminó; prohibido sustituir por cierre del padre |
| Replay/variante/neto | Bloqueados | Ninguna ejecución económica aprobada |

47 intentos dRPC acumulados: 9 previos + 38 en este turno; 46 cuerpos exitosos y un rechazo del túnel sin cuerpo RPC. Se mantienen además 6 intentos históricos PublicNode (53 intentos totales del expediente, no 53 éxitos). Cero consultas después del rechazo. Las nueve llamadas previas no tenían timestamp individual; se informa su ventana de adquisición, no se inventa precisión.
