from pathlib import Path
import json,hashlib,datetime,subprocess,collections,shutil
P=Path(__file__).resolve().parent
E=P/'evidence'
def put(name,value):
 p=P/name;p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n' if not isinstance(value,str) else value,encoding='utf-8')
def norm(n,d):
 sign='-' if n<0 else '';n=abs(n);return sign+str(n//10**d)+'.'+str(n%10**d).zfill(d)
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
rows=[json.loads(s) for s in (E/'prior_run/rpc_history.jsonl').read_text().splitlines()]
requests=[]
rawdir=E/'rpc_preserved';rawdir.mkdir(exist_ok=True)
for row in rows:
 raw=row['raw_response_text'].encode();assert sh(E/'prior_run/rpc_history.jsonl')=='42c5d95ad7ac5e60497dc03f10a2661f66db542c5184ead84ba996adf4468fab'
 assert hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['body_bytes']
 name=f"evidence/rpc_preserved/prior_{row['attempt']:02}.json";(P/name).write_bytes(raw)
 requests.append({'origin_run':39453561233,'endpoint':row['endpoint'],'request':row['request'],'http_status':row['http_status'],'rpc_status':'RESULT_PRESENT','bytes':len(raw),'sha256':row['sha256'],'body_path':name,'timestamp_utc':None,'timestamp_window_utc':['2026-10-20T16:00:24.2266545Z','2026-10-20T16:00:27.2062857Z'],'timestamp_note':'The prior recorder did not capture individual request timestamps; window from full job log.'})
probe=json.loads((E/'capability_balance_probe.json').read_text());requests.append({**probe,'body_path':'evidence/'+probe['body_path'],'rpc_status':'RESULT_PRESENT'})
network=[json.loads(s) for s in (E/'continuation_historical_metadata/network.jsonl').read_text().splitlines()]
for row in network:
 r=dict(row);r['body_path']='evidence/continuation_historical_metadata/'+r['body_path'] if r.get('body_path') else None;r['rpc_status']='TRANSPORT_DENIED_NO_RPC_RESPONSE' if r.get('error') else 'RESULT_PRESENT';requests.append(r)
assert len(requests)==47
success=[r for r in requests if r['rpc_status']=='RESULT_PRESENT'];assert len(success)==46
wire=json.loads((E/'offline/CHAIN_INTEGRITY.json').read_text())
receipt=json.loads(rows[1]['raw_response_text'])['result'];prefix=json.loads(rows[4]['raw_response_text'])['result']
full=json.loads((E/'continuation_historical_metadata/response_11.bin').read_text())['result']
parent=json.loads(rows[2]['raw_response_text'])['result']
final=json.loads((E/'continuation_historical_metadata/RESULT.json').read_text())
miss=json.loads((E/'offline_reproduction/RESULT.json').read_text())['missing'][0]
counts=collections.Counter(r['request']['method'] for r in success)
put('EVIDENCIA_CANONICA.json',{'schema':'nqc068-evidence-inventory-v1','created_utc':now,'repository':'josuechavando350-png/nexus-quant-capital','reviewed_parent':'b5f263c3b620c7ad8f81f3a205288f52b0baf605','chain_id':1,'target_block':21762897,'parent_block':21762896,'target_hash':full['hash'],'parent_hash':parent['hash'],'target_transaction':receipt['transactionHash'],'prefix_transaction':prefix['transactionHash'],'target_index':1,'target_timestamp_utc':'2025-02-03T02:07:35Z','target_environment':{k:full[k] for k in ['timestamp','baseFeePerGas','gasLimit','miner','mixHash','parentBeaconBlockRoot','stateRoot','receiptsRoot','transactionsRoot']},'independent_hash_verification':wire,'receipt_identity':{'target_status':receipt['status'],'target_gas_used':int(receipt['gasUsed'],16),'target_effective_gas_price_wei':int(receipt['effectiveGasPrice'],16),'target_logs':len(receipt['logs']),'prefix_status':prefix['status'],'prefix_gas_used':int(prefix['gasUsed'],16),'prefix_logs':len(prefix['logs'])},'sufficiency':'BLOCKED_EVIDENCE','complete_parent_state':False,'complete_pretransaction_state':False,'prefix_execution_completed':False,'receipt_trie_membership_verified':False,'state_account_storage_proofs_verified':False,'consensus_finality_independently_verified':False,'evidence_grade':'RPC bodies retained and hash checked; block header and all 41 transaction hashes/root recomputed; receipt identity checked but no receipt MPT proof; partial account/storage only. Not a complete canonical execution witness.','counts':{'prior_publicnode_attempts':6,'prior_drpc_attempts':9,'this_turn_drpc_attempts':38,'combined_drpc_attempts':47,'combined_all_rpc_attempts':53,'drpc_successful_preserved_bodies':46,'drpc_transport_denials':1,'new_attempts_after_denial':0,'successful_drpc_by_method':dict(counts)},'requests':requests,'first_missing_read':miss,'transport_failure':network[-1],'failure_attribution':'Tunnel connection returned 403 Forbidden; cannot attribute denial to dRPC application or infer archive/pruning/quota cause. No JSON-RPC envelope or body was received.','local_metadata_adapter':'eth_blockNumber derived from retained target header; eth_gasPrice derived from retained original receipt. Both explicitly local, no upstream latest read, no modified contract state.','closed':True,'commercial_admission':False})

assets={'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2':('WETH',18),'0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48':('USDC',6),'0x1f9840a85d5af5bf1d1762f925bdaddc4201f984':('UNI',18)}
transfer='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
withdraw='0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65'
executor='0x8ce45e650ab17b6ca0dd6071f7c2b5c69b5b42b2';gas_payer='0x0ef3794cb89864337e15a9f077020c285ef0989b'
journal=[];deltas=collections.defaultdict(lambda:collections.defaultdict(int))
def entry(asset,debit,credit,amount,basis,log_index=None):
 decimals=6 if asset=='USDC' else 18
 journal.append({'asset':asset,'from_account':debit,'to_account':credit,'amount_base_units':str(amount),'amount':norm(amount,decimals),'debit_delta_base_units':str(-amount),'credit_delta_base_units':str(amount),'basis':basis,'log_index':log_index})
 deltas[asset][debit]-=amount;deltas[asset][credit]+=amount
for ev in receipt['logs']:
 if ev['topics'][0]==transfer:
  asset,_=assets[ev['address']];entry(asset,'0x'+ev['topics'][1][-40:],'0x'+ev['topics'][2][-40:],int(ev['data'],16),'ORIGINAL_RPC_RECEIPT_TRANSFER_EVENT_NOT_LOCAL_REPLAY',int(ev['logIndex'],16))
 elif ev['topics'][0]==withdraw:
  entry('WETH','0x'+ev['topics'][1][-40:],'WETH_REDEMPTION_CLEARING',int(ev['data'],16),'ORIGINAL_WITHDRAWAL_EVENT; ETH native transfer not independently traced here',int(ev['logIndex'],16))
gas=int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16)
entry('ETH',gas_payer,'ETH_BASE_FEE_BURN',gas,'DERIVED_FROM_ORIGINAL_RECEIPT; base fee equals effective gas price, priority fee zero')
assert all(sum(a.values())==0 for a in deltas.values())
slot=int(json.loads(rows[8]['raw_response_text'])['result'],16);r0=slot&((1<<112)-1);r1=(slot>>112)&((1<<112)-1)
out_usdc=int(receipt['logs'][1]['data'],16);sync=receipt['logs'][2]['data'][2:];post0=int(sync[:64],16);post1=int(sync[64:],16);original_weth_in=int(receipt['logs'][0]['data'],16)
put('CONTABILIDAD_INTEGRAL.json',{'schema':'nqc068-accounting-with-explicit-unknowns-v1','verdict':'NETO_NO_DETERMINABLE','variant_executed':False,'variant_gas_receipt':None,'variant_net_amount':None,'variant_net_asset':None,'realized_nqc_profit_demonstrated':{'amount':'0','scope':'No NQC settlement demonstrated in this investigation; not an audit of all NQC accounts'},'actual_total_nqc_profit':None,'participants':{'flash_originator':'Uniswap V2 USDC/WETH pair in proposed variant only','executor':{'historical_address':executor,'variant_address':None},'borrower':'0x8dca753a1f0918061ea27e69645a189d3ee1d53c','Morpho':'0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb','V2':'0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc','V3':'0x1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801','historical_gas_payer':gas_payer,'historical_coinbase':full['miner'],'sponsor':None,'NQC_beneficiary':None,'economic_ownership_consolidation_proven':False},'historical_original_partial_double_entry_journal':journal,'historical_deltas_base_units':{asset:{account:str(v) for account,v in accounts.items()} for asset,accounts in deltas.items()},'journal_balanced_per_asset':True,'journal_scope':'Original historical Transfer/Withdrawal logs and original receipt gas only. Opening/closing balances, native inclusion transfer, borrower debt-share stock and external obligations are not fully reconciled; this is not variant economics. WETH and ETH remain separate.','historical_reference_not_variant_result':{'executor_WETH_after_withdrawal':norm(deltas['WETH'][executor],18),'executor_USDC_dust':norm(deltas['USDC'][executor],6),'gas_ETH_paid_by_separate_sender':norm(gas,18),'inclusion_ETH_from_prior_explorer_transcription_only':'12.447536358167279703','prior_consolidated_ETH_equivalent_conditional':'1.915425887007584330','conditions':['WETH redeemable 1:1 to ETH','common economic ownership of gas payer/executor not established','inclusion native transfer taken from prior explorer transcription, no new native trace','other costs unknown'],'NQC_income':False},'historical_V2_reserve_observation':{'at_parent_block':21762896,'slot':'0x8','reserve0_USDC_base':str(r0),'reserve1_WETH_base':str(r1),'blockTimestampLast':slot>>224,'reserve_implied_by_target_Sync_minus_Swap':[str(post0+out_usdc),str(post1-original_weth_in)],'agreement':r0==post0+out_usdc and r1==post1-original_weth_in,'mathematical_minimum_WETH_for_requested_USDC':str(r1*out_usdc*1000//((r0-out_usdc)*997)+1),'is_executed_flash_swap':False,'warning':'Parent state and receipt arithmetic agree; this does not execute prefix, callbacks or variant.'},'unpriced_variant_obligations':{k:None for k in ['flash_repayment_executed','actual_V3_output','full_intrinsic_and_execution_gas','deployment_gas','approvals_gas','maximum_upfront_gas','inclusion_payment','sponsor_advance','sponsor_fee','revert_cost','reorg_liability','noninclusion_liability','infrastructure_attribution','beneficiary_liquidity_cost']},'sponsor_status':'SPONSOR_UNCONFIRMED','unknown_costs_treated_as_zero':False,'fees_double_counted':False,'sensitivities':'NOT_RUN: A failed on missing evidence; no measured variant inputs. No fabricated net, break-even or monthly projection.'})

matrix=[('Recibo objetivo','Disponible', '11 logs; 602029 gas; status 1; sin prueba de inclusión de recibo'),('Recibo tx0','Disponible','76 logs; 1624673 gas; status 1; no reproduce tx0'),('Cuerpos tx0 y tx1','Verificados por hash','RLP firmado histórico y recuperación del firmante; cero firmas nuevas'),('Bloques padre/objetivo','Hashes recomputados','RLP de cabeceras coincide; consenso independiente no comprobado'),('Bloque completo objetivo','41 transacciones verificadas','Raíz transactionsRoot recomputada e idéntica'),('Código al padre','Parcial','9 respuestas de cuentas; dos son 0x legítimos de EOA/precompilado'),('Saldo ETH al padre','Parcial','9 respuestas; no cubren todos los participantes'),('Nonce al padre','Parcial','8 respuestas'),('Storage al padre','Parcial','12 respuestas; primera ausencia exacta: router slot 0x3'),('Preestado inmediato tx1','No disponible','tx0 no terminó; prohibido sustituir por cierre del padre'),('Replay/variante/neto','Bloqueados','Ninguna ejecución económica aprobada')]
put('MATRIZ_RPC.md','# Matriz de disponibilidad histórica\n\nCaso Ethereum 21762897, índice 1. Respuestas conservadas; detalles por llamada en EVIDENCIA_CANONICA.json.\n\n| Dato | Estado | Alcance |\n|---|---|---|\n'+''.join('| '+' | '.join(r)+' |\n' for r in matrix)+'\n47 intentos dRPC acumulados: 9 previos + 38 en este turno; 46 cuerpos exitosos y un rechazo del túnel sin cuerpo RPC. Se mantienen además 6 intentos históricos PublicNode (53 intentos totales del expediente, no 53 éxitos). Cero consultas después del rechazo. Las nueve llamadas previas no tenían timestamp individual; se informa su ventana de adquisición, no se inventa precisión.\n')

put('RESULTADO_COMERCIAL.md',f'''# NQC068 - Resultado comercial integral

**BLOCKED_EVIDENCE. Decisión: CONGELAR EL REPLAY. MALO para la meta de ingresos: rentabilidad propia no demostrada. No es una refutación económica del flash swap.**

Fecha del dictamen: {now}. Padre revisado: `b5f263c3b620c7ad8f81f3a205288f52b0baf605`. Caso único: Ethereum 21762897 / tx índice 1 / `{receipt['transactionHash']}`.

| Puerta | Dictamen | Evidencia |
|---|---|---|
| A. Original auténtico | BLOQUEADO | Se inició la reconstrucción EVM; tx0 no terminó por falta de storage tras rechazo 403 del túnel. |
| B. Principal propio cero | BLOQUEADO / NO EJECUTADO | No se ejecutó variante sobre baseline incompleto. |
| C. Neto contrafactual | NETO NO DETERMINABLE | Gas de variante, fills ejecutados y obligaciones no medidos. |
| D. Financiación comercial | PENDING / SPONSOR_UNCONFIRMED | Documentación pública de Titan; ninguna aceptación específica ni términos de responsabilidad NQC. |
| E. Ganancias reales NQC | NO DEMOSTRADAS | 0 de ganancia realizada demostrada en este expediente; ninguna operación NQC transmitida. |

## Avance verificable de este turno

El informe anterior de tres runs quedó desactualizado: el cuarto run `39453561233` había conseguido nueve respuestas dRPC y fallado localmente por `eth_blockNumber`. Recuperé íntegros sus 33 fragmentos comprimidos (SHA256 `89e0e2a89f8af22016ef94408262e45837749388b9968a34f6163ede8894229e`), ocho archivos y los nueve cuerpos RPC. Ninguno se había conservado en el informe anterior.

Se adaptó exclusivamente la inicialización local de Foundry: altura desde la cabecera histórica y precio desde el recibo original, ambos etiquetados como metadatos derivados. Los seis archivos fuente originales, Solidity y expectativas se conservaron byte por byte. Compilación local con Foundry 1.3.1 y solc 0.8.26. Se verificaron por cálculo los hashes de ambas cabeceras, los hashes de las 41 transacciones y su raíz `transactionsRoot`. Los firmantes de tx0/tx1 se recuperaron de sus firmas históricas, sin crear firmas.

La continuación conservó 37 cuerpos exitosos nuevos (una lectura inicial de saldo y 36 durante el fork). El intento siguiente falló al leer:

```
eth_getStorageAt(
  0x111111125421ca6dc452d289314280a0f8842a65,
  0x3,
  0x14c1350
)
URLError: <urlopen error Tunnel connection failed: 403 Forbidden>
```

El error lo produjo el túnel de conexión: no hay cuerpo JSON-RPC que permita atribuirlo al archivo de dRPC, a una cuota o a la retención del nodo. No se cambió origen, IP, sesión, credenciales ni transporte para eludirlo. La ejecución offline posterior, con las 46 respuestas exitosas conservadas y cero red, vuelve a detenerse exactamente en ese mismo slot. Baseline sin aprobar; variante sin ejecutar.

## Respuestas obligatorias al fundador

1. **¿Se reprodujo el original? BLOQUEADO.** Se intentó; la reconstrucción de tx0 no terminó. Exit code 1 y traza en `evidence/continuation_historical_metadata/baseline.log`; bloqueo reproducido en `evidence/offline_reproduction/`.
2. **¿Funcionó sin principal? BLOQUEADO.** No existe transacción local de variante ni estado inicial de un ejecutor nuevo efectivamente probado.
3. **¿Cuánto dejó neto? DESCONOCIDO.** Ningún neto de variante medido. Los 1.915425887007584330 ETH equivalentes pertenecen a una consolidación histórica condicionada de un tercero; no son resultado NQC.
4. **¿Quién financia gas? NO CONFIRMADO.** Titan describe patrocinio condicionado, pero no hay aceptación NQC, precio, prioridad de cobro ni cobertura acreditada de fallos/reorgs.
5. **¿Cuánto ganó NQC realmente? 0 demostrado en esta investigación.** El beneficio total real de NQC fuera de ella no fue auditado.
6. **¿Continuar o congelar? CONGELAR el replay online.** Hace falta un único paquete/testigo completo verificable del estado padre y dependencias de tx0/tx1, obtenido por vía permitida. Un slot aislado desbloquearía solo el primer acceso, no garantiza completar el caso.
7. **¿Es BUENO o MALO? MALO comercialmente hoy.** Bueno como avance de evidencia: se rescataron los datos y se localizó y reprodujo el bloqueo. No hay prueba de beneficio ni compromiso de financiación.

Confianza: **alta** en la identificación del bloqueo y en los datos íntegros conservados; **indeterminada** en la viabilidad/rentabilidad de la variante. No hay fundamento para asignar una probabilidad de ingreso ni proyectar mensualidades.

## Límites de autenticidad y aislamiento

Los hashes de cabeceras y transacciones no prueban por sí solos consenso ni la totalidad del estado. No se verificaron pruebas Merkle de cuentas/storage ni la raíz de los 41 recibos. Las respuestas RPC son evidencia primaria conservada de lo que el proveedor entregó, no un testigo canónico completo.

`main` permanece en `16e352225ba8a6a931834c4edf3d86d9a2924b7d`. El verificador del baseline pasa y sus nueve tests pasan. El verificador del árbol de investigación **falla** por el workflow activo heredado del padre revisado, sin modificarlo; sus tests dan siete aprobados y dos errores. Esta rama no activa ni modifica workflows. No se tocó ningún archivo previo, permisos, secretos ni otro repositorio. No hubo firma, broadcast, operación financiera, patrocinio solicitado ni gasto autorizado.

Ver `EVIDENCIA_CANONICA.json`, `CONTABILIDAD_INTEGRAL.json`, `REPLAY_ORIGINAL.md`, `REPLAY_CERO_PRINCIPAL.md`, `PRUEBAS_Y_AISLAMIENTO.md` y `BLOQUEOS_ACCIONABLES.md`.
''')
put('REPLAY_ORIGINAL.md','''# Original - ejecución real bloqueada

## Identidad y herramientas

Productor de antecedente: run 39453561233 / job 118734415837 / commit b5f263c3b620c7ad8f81f3a205288f52b0baf605. Sus logs completos están en evidence/prior_run/log_118734415837.log. Los tres runs anteriores también se conservan íntegros como logs, sin inventar los cuerpos que no exportaron.

Fuente: source_bundle SHA256 712bc3461b04bb6411947ae0bed68704de2ff825e29ba05ee31d47f7c8918514; seis hashes verificados en evidence/SOURCE_INTEGRITY.json. Foundry 1.3.1 (commit 08d3a4ad4d78b62bcb897350803bf96fc2cf6cc9); solc 0.8.26+commit.8a97fa7a. Archivo oficial Foundry SHA256 baad3e1b06d6f310d210c93e95258a03d923fe610f8d0742138f2245f94abd7c; solc SHA256 d5f23436f443edb85d8e76906d12f0a86ce0490e7663a9e608efeb7a93f149ef. Compilación local original: exit 0, dos archivos en 2.34 segundos según salida del comando. Los replays posteriores reutilizaron esa compilación.

## Secuencia real de intentos

| Intento | Lecturas upstream nuevas | Resultado |
|---|---:|---|
| Metadato de altura local | 0 | setUp falla en eth_gasPrice. |
| Flag --gas-price histórico | 0 | Foundry sigue pidiendo eth_gasPrice al inicializar. |
| Altura y gas históricos locales | 37 | 36 respuestas HTTP 200; fallo de túnel en lectura 47 dRPC acumulada. |
| Reproducción offline posterior | 0 | Falla exactamente en el mismo slot ausente. |

La consulta inicial de saldo en este turno fue una lectura adicional exitosa, fuera de la tabla: total del turno 38 intentos. Total dRPC 47; PublicNode previo 6. Los primeros dos fallos locales no generaron reintentos upstream.

Comando económico intentado (rutas concretas completas en RESULT.json):

```bash
forge test --offline --use /ruta/verificada/solc --gas-price 302819782345 \
  --match-contract HistoricalFlashReplayTest --match-test '^test_01_' -vvvv
```

El test mantiene createSelectFork por hash de la transacción objetivo: Foundry intenta el prefijo antes de tx1. No se sustituyó el preestado por el cierre del padre. Duración del intento: 114.864483932 s; exit 1; se detuvo en setUp, antes de la liquidación objetivo. No se obtuvo receipt local original, paridad final, traza económica completa ni comparación completa de gas/saldos.

Primer punto de divergencia: lectura histórica de storage 0x3, cuenta 0x111111125421ca6dc452d289314280a0f8842a65, bloque padre 21762896. No es un revert de protocolo, déficit de devolución ni cambio de precio: falta una dependencia de estado tras un rechazo de transporte.

Reproducción sin red:

```bash
python3 reproduce_offline.py /ruta/de/binarios/verificados
```

Resultado conservado: 46 respuestas exitosas disponibles; mismo primer acceso faltante; exit 1; cero red. El script de continuación online se publicó bloqueado por el estado terminal registrado. No ejecutar las copias históricas de fuentes como una nueva autorización de red.

## Lo contrastable y lo pendiente

Se conservaron y verificaron identidades de recibos, bloques, orden y transacciones; se decodificaron los eventos históricos y sus cantidades. Se leyó reserve0=38669555298186 y reserve1=16417414753955494219446 en slot 8 de V2 al padre, compatibles con el Sync/Swap original. Es evidencia más fuerte que una transcripción, pero no completa tx0.

No se ejecutaron las aserciones de oráculo, parámetros Morpho, saldo inicial del ejecutor original ni resultados finales: setUp no llegó a ellas. El recibo remoto con status 1 prueba el dato histórico reportado por RPC, no que el replay local haya pasado.
''')
put('REPLAY_CERO_PRINCIPAL.md','''# Variante cero principal - NO EJECUTADA

Estado: BLOCKED_BY_ORIGINAL. No hay tx local, receipt, gas medido, callbacks ejecutados, deuda pagada ni flash swap devuelto por la variante. La puerta A no pasó y por ello no se lanzaron test_02, test_03 ni test_04.

Se conservan sin modificar HistoricalFlashExecutor.sol y HistoricalFlashReplay.t.sol como fuentes previas. La variante propuesta solicita 616687327559 unidades USDC del V2 original, liquida la misma posición Morpho y vende UNI mediante V3 antes de devolver WETH. Esta descripción del código no afirma ejecución.

La lectura real del slot 8 de V2 al padre permite contrastar aritméticamente 266862310264222944156 wei WETH como mínimo del modelo V2 para ese output. La coincidencia no sustituye el prefijo, el oráculo, la ejecución V3 ni la invariante al finalizar el callback.

Pendientes: capital inicial cero comprobado en un ejecutor efectivamente desplegado en el fork, callbacks autenticados y spoofing, devolución atómica, slippage, 1 wei, insuficiencia de saldo, rollback completo, receipt íntegro, coste intrínseco/deployment/aprobaciones y saldo del beneficiario. Ninguna prueba pendiente se marca PASS.

Limitación adicional de la fuente heredada: sponsorPayment=0 aisla la ruta de tokens; gasleft mide scopes internos, no un receipt facturado. Incluso si esos tests pasaran en el futuro, habría que completar los requisitos de logs, recibos, costes y financiación de la Directiva 068 para aceptar B/C/D.
''')
put('BLOQUEOS_ACCIONABLES.md','''# Bloqueos accionables del mismo caso

## Bloqueo inmediato y pieza mínima externa

**Se necesita un único paquete/testigo histórico completo verificable** para Ethereum bloque padre 21762896, con código, balances, nonces y storage de todas las dependencias ejecutadas por tx0 y tx1; transacciones y cabeceras ancladas; evidencia suficiente para comprobar la transición del prefijo. Debe cubrir también la ruta de la variante cuando A permita probarla. No se pide una lista de oportunidades ni una suscripción.

Las 46 respuestas ya conservadas deben reutilizarse. El primer dato faltante identificado es el slot 0x3 de 0x111111125421ca6dc452d289314280a0f8842a65 al padre. **Entregar únicamente ese slot no garantiza que sea el último que falta.** Un recibo, ABI, código fuente, etiqueta del explorador o estado latest no sustituyen este paquete.

Causa observada: túnel de conexión rechazado con 403 durante esa lectura. Causa del control de acceso y capacidad completa del nodo: no determinadas. No reintentar por otras IP, sesión, proxy, credenciales, runner ni proveedor para eludir el rechazo. Con las restricciones vigentes, el replay online está congelado. La siguiente acción útil es aportar el testigo por una vía permitida; después, validarlo offline y repetir original antes de variante.

## Pendientes comerciales posteriores, no bloqueos inventados del replay

Si A y B pasan, medir receipt completo de variante y todas las obligaciones. Solo después evaluar C. La documentación pública de Titan no es una aceptación NQC: D requiere compromiso, precios, preferencia de cobro y asignación de pérdidas/reorgs/revertidos. Se conserva SPONSOR_UNCONFIRMED, sin contactar operadores ni enviar bundles. Ninguna evidencia técnica autoriza E en esta investigación.
''')
put('FINANCIACION.md','''# Financiación - SPONSOR_UNCONFIRMED

Consulta de documentación oficial el 20 de octubre de 2026: https://docs.titanbuilder.xyz/api/eth_sendbundle (sección Sponsored Bundles). Describe un anticipo ETH ante insuficiencia de gas/value condicionado a recuperar su coste y aumentar el saldo del builder. Esto explica un mecanismo; no documenta aceptación de este paquete NQC.

| Obligación | Responsable/condición acreditada para NQC |
|---|---|
| Principal del flash swap | Solo propuesto a cargo del V2; no ejecutado en fork. |
| Gas inicial y límite máximo | No confirmado. |
| Gas consumido y coste del anticipo | No cotizado ni medido para la variante. |
| Gas de despliegue/aprobación | No medido; debe separarse si corresponde a otra transacción. |
| Revertidos, reorgs y bundles excluidos | Reparto de responsabilidad no confirmado. |
| Prioridad de recuperación y remuneración del sponsor | Sin términos específicos. |
| Recurso personal contra el fundador | No acreditado como inexistente. |

No se solicitó financiación ni se contactó al builder. No se firmó ni envió paquete alguno. La documentación pública no acredita la rentabilidad de NQC. Los campos monetarios desconocidos quedan null, nunca cero.
''')
put('PRUEBAS_Y_AISLAMIENTO.md','''# Pruebas e identidad - sin certificación económica

Padre de la nueva rama: b5f263c3b620c7ad8f81f3a205288f52b0baf605, árbol 960a7a260a131693cfac49b234a58e772a88a22f; padre del padre df29f5539910caae90604c0f6c39292998074f0c. Main auditada: 16e352225ba8a6a931834c4edf3d86d9a2924b7d. Ramas/commits observados completos en evidence/github_initial.json y evidence/github_logs_metadata.json.

| Verificación | Resultado real |
|---|---|
| Seis fuentes frente al MANIFEST y bundle Git | PASS, bytes y SHA256 idénticos. |
| Bundle comprimido de evidencia del cuarto run | PASS, 33 fragmentos, 49169 bytes, SHA256 y ocho archivos recuperados. |
| Hash RLP de dos cabeceras | PASS. |
| Hash de 41 transacciones y raíz de trie | PASS. No prueba consenso por sí mismo. |
| Recuperación de firmantes tx0/tx1 | PASS, firmas históricas. |
| Guard original / wrapper de archivo | 12 + 6 tests offline aprobados localmente; pruebas de transporte. |
| Adaptador y prohibición de reintento tras 403 | 7 tests offline aprobados. |
| Compilación Solidity original | PASS, solc 0.8.26, 2 archivos. |
| Verificador original en worktree main | PASS, 531 fuentes y 106 workflows deshabilitados; no recertificación original. |
| Tests de aislamiento en main | 9/9 PASS. |
| Verificador global en rama de investigación | FAIL: forbidden active/client tree. Workflow previo conservado. |
| Tests de aislamiento en rama de investigación | 7 PASS, 2 ERROR: directorio workflow ya existente y rechazo del árbol activo. No se alteró el test. |
| Original EVM | FAIL de infraestructura/evidencia en setUp; cero pruebas económicas aprobadas. |
| Reproducción offline del bloqueo | Mismo primer slot faltante; original sigue FAIL; cero red. |
| Variante, seguridad, gas, sensibilidad/neto | NO EJECUTADOS porque A no pasó. |
| Rust / certificación completa PFT-Census | NO EJECUTADOS, fuente original intacta; no afirmamos certificación. |

Todos los cambios de este turno son adiciones bajo migration/experiments/nqc-068-commercial-proof-20261020/. No se modifican fuentes previas, main, otros repositorios, workflows, clientes, secretos ni permisos. No se activan pipelines: el workflow existente tiene branch/path exactos distintos de esta rama y no se toca. Auditoría final de rutas y commit en GIT_PUBLICATION.json / evidence/git_scope.json. Los archivos de evidencia no autorizan ejecutar viejos productores.

Los logs de ejecución contienen hashes de herramientas; TOOLS_AND_BUILD.json conserva hashes locales de binarios y compilados. SHA256SUMS cubre entregables y evidencia salvo sí mismo; PUBLICATION se añade después como registro del commit inicial, sin prometer un hash circular del propio commit.
''')
print('Deliverables created; successes',dict(counts))
