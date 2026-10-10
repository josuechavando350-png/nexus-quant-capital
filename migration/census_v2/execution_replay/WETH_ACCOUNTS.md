# Nueve casos WETH: separar cuentas, retiros y gas

Readback offline del 10 de octubre de 2026. **No es P&L ni admisión de Nexus.**
Los nueve casos históricos completos se conservan, sin elegir sólo los positivos.
Se reconstruyen 97 filas transacción/cuenta, 26 movimientos nativos y diez
retiros WETH a partir de las trazas y recibos ya autenticados. No hubo consultas
RPC nuevas. Los seis insumos y seis dependencias directas se fijan al commit
`fb49a9c46bb52997c689ba2b7f183c4e536a9cb9`; sus SHA-256 constan en el informe.

## Hallazgo y alcance

En los rangos retrospectivos **2, 3, 4 y 5**, el flujo WETH por transferencias
del ejecutor difiere de colateral menos deuda de la liquidación seleccionada.
Las transacciones pueden contener otros intercambios o transferencias: ni el
retiro completo ni el saldo de un destinatario se atribuyen automáticamente a
esa única liquidación. Otros activos permanecen en unidades propias, sin
sumarlos a WETH/ETH ni valorarlos con un precio de cierre.

El cuadro usa unidades enteras de wei y **deltas observados**, no pruebas de
saldos completos. Ejecutor y remitente son direcciones distintas; no se asume
que tengan el mismo propietario. El gas sólo se carga al remitente.

| Rango histórico | WETH del ejecutor después del retiro | ETH del ejecutor antes de gas | WETH del remitente | ETH del remitente después de gas |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 9,975 | 0 | -19,694,395,589,351 |
| 2 | 1,151,432,197,192,748 | 0 | 0 | -523,017,715,007,964 |
| 3 | 0 | 228,380,081,613,572 | 0 | -216,584,522,059,332 |
| 4 | -3,379,677,466,555,340 | 0 | 0 | 3,862,366,547,395,285 |
| 5 | 0 | 0 | 1,195,892,022,161,724 | -860,823,959,225,521 |
| 6 | 45,195,368,810,059 | 9,348 | 0 | -33,774,361,249,994 |
| 7 | 447,579,828,503,859 | 2,567 | 0 | -340,842,986,171,186 |
| 8 | 87,092,929,974,617 | 583 | 0 | -59,313,561,071,935 |
| 9 | 184,412,003,120,424 | 107 | 0 | -184,412,003,017,232 |

En el caso 1, los 9,975 wei nativos del ejecutor son exactamente el débito
nativo del remitente antes de gas; no son un nuevo ingreso creado por la ruta.
El WETH retirado se debita antes de calcular su delta, evitando contarlo a la
vez como token retenido y como ETH. Los pagos a otras direcciones permanecen
separados y sin atribución de propiedad. El delta WETH negativo del ejecutor en
el caso 4 exige explicar inventario/estado; no se promueve a autofinanciación.

En el caso 5, el evento Balancer y los logs de transferencia concilian una
entrega y devolución de **342,642,361,343,309,991 wei WETH**, con comisión
observada cero. Se comprueba cantidad, emisor/receptor y orden de logs. Esto
corrobora las dos transferencias del préstamo histórico, no balances, acceso
de Nexus, capacidad disponible ni ausencia de otras obligaciones. La ausencia
de eventos reconocidos en los otros ocho casos no significa financiación gratis
ni ausencia de préstamo; las rutas no reconocidas siguen sin resolver.

## Controles y reproducción

Se vuelven a analizar las trazas originales, no sólo el informe derivado. Cada
log se liga a transacción/bloque/posición y se rechazan logs removidos, repetidos
o desordenados. Se excluyen valores heredados de delegatecall y ramas revertidas.
Los retiros coinciden por destinatario, cantidad y multiplicidad con los recibos.
Los eventos WETH no soportados fallan explícitamente; este consumidor no afirma
cobertura general de depósitos ni de todas las variantes de tokens.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/reconcile_weth_accounts.py \
  --out /absolute/path/fresh-weth-account-readback
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2/execution_replay -p 'test_*.py' -v
```

Dos ejecuciones producen ledger e informe idénticos. El ledger tiene SHA-256
`7698bdfaaeb9e8f95eb9e9eacf55499c9444743fb33e516269e5d867828a7c4f`.
Pasan **42 controles Python afectados**, incluidos 15 nuevos. La verificación
contra objetos Git originales conserva las 637 entradas y cero workflows
activos. Las nueve pruebas de aislamiento fallaron inicialmente al copiar sus
fixtures por falta de disco; `isolation-disk-full.log` conserva el fallo entero.
La misma suite, sin modificar ni omitir archivos, pasa usando `TMPDIR` en un
directorio temporal nuevo de `/dev/shm`. Los logs finales están en `weth-accounts/`.
Rust y Solidity no cambiaron ni se ejecutaron en este incremento.

No se prueban saldos de estado, propietarios, todas las obligaciones, costes
completos, disponibilidad antes de decidir, captura o financiación inicial del
gas. `complete_profit_wei` sigue `null` y los nueve casos siguen
`INSUFFICIENT_EVIDENCE`. No se altera el ledger original ni la política MXN
2,000. Este incremento no satisface 10/20, 15/20 o 20/20 ni cierra Census.

La continuación `WETH_INVENTORY.md` reconstruye los mínimos de inventario inicial
por orden de logs sobre las mismas cuentas, sin convertir estos deltas en
pruebas de estado ni promover financiación.

`TRACE_LOANS.md` añade la conciliación de llamadas de préstamo retenidas en las
127 trazas contra transferencias de recibos; incluye los rangos WETH 1, 3, 6, 7
y 8. Los límites de financiación, costes y admisión anteriores siguen abiertos.
