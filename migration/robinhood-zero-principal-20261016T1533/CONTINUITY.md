# Continuidad NQC — 16/oct/2026, auditoría de financiación

Repositorio único: `josuechavando350-png/nexus-quant-capital`.
Rama: `nqc/zero-principal-audit-20261016T1533`.
PR23: https://github.com/josuechavando350-png/nexus-quant-capital/pull/23.
Commit de código/evidencia: `5b5f310e6e8e02e47be3b82e2698fe2ef842057b`.
Árbol de evidencia: `8948ac64360563588adf46425b04725270735298`.
El commit posterior de relevo sólo añade estas referencias y actualiza el manifiesto.
Base PR22: `0fe92f34c863feba59a674c561fa6ebea80c278b`.
Buscar PR/commits posteriores antes de continuar. Leer AGENTS.md y README de este
incremento. No repetir auditoría histórica como oportunidad o ingresos nuevos.

## Incremento cerrado

Prioridad explícita de Chavando: no tiene capital propio; distinguir principal,
gas y riesgo de fallos. Incremento enteramente offline, **0 RPC/0 s de captura**.
Documentación pública actual consultada sin contactos, cuentas, gastos o envíos.

Nuevo auditor autentica 251 archivos, vuelve a ejecutar auditores offline previos
y verifica cronología de caja, no sólo deltas finales. En la simulación histórica
NQC del bloque66744162/hash8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7,
índice1 (19/sep/2026): seis lecturas iniciales cero (ejecutor USDG/wsNET; router
USDG/wsNET/sNET/NET), ocho series de balances con cero adelanto y cero saldo final.
Morpho transfiere colateral antes de `onMorphoLiquidate`, se vende dentro, después
pull de194.034131USDG. Venta226.094796; excedente32.060665USDG antes de gastos.
Un `liquidate` de ejecución, cinco STATICCALLs adicionales preservados; no un
`flashLoan` Morpho separado. No generalizar a todas las rutas, ni confundir este
contrafactual con ejecución real de NQC o beneficio.

Nuevo modelo de cuatro resultados: éxito, UserOp incluida fallida, bundle incluido
revertido y rechazo sin envío. Distingue financiador integrado vs bundler externo;
no duplica débito paymaster y red. Probabilidades, cotización, gastos y términos
deben ser explícitos. Los ejemplos sólo son tests sintéticos. Falta una entrada
prospectiva válida; el resultado comercial permanece desconocido/bloqueado.

Casos Nitro históricos reautenticados, sin nueva EVM/RPC:
- Ventana31s éxito: red0.000055018306338ETH; sponsor0.000076653394686ETH.
- UserOp fallida, variante original en padre: red0.000039639718050ETH;
  sponsor0.000050201161200ETH. Es otra variante, no comparación homogénea.
- Bundle vencido: sponsor0 pero bundler pierde0.000005878984092ETH.
- Rechazo antes de envío: cero gas de red por definición, costes externos desconocidos.
No usar esos tres casos seleccionados para estimar frecuencias de éxito/fallo.

La reserva histórica249541240000000wei no es capital actual ni presupuesto total.
0.1ETH EntryPoint/0.01ETH bundler son fixtures, no fondos obtenidos ni mínimos.
Financiación, stake/admisión, términos sin recurso, cobro/reparto/reposición de ETH,
costes fijos/conversión y captura rentable siguen pendientes.

PROVIDERS.md: Alchemy anuncia Robinhood pero cobra; ZeroDev tarjeta/créditos;
Unlinked operador financiado, relay propio y Simple7702Accountv0.9, sin admisión
NQCv0.7 demostrada. Sus cotas testnet no se atribuyen a mainnet. Una página oficial
Robinhood no fue accesible por buscador; se registra, no se inventa verificación.
FINANCING.md contiene requisitos internos; no oferta/contrato/contacto enviado.

85 pruebas Python distintas aprobadas:24nuevas+16replay+16window+20economics+9isolation.
Dos intentos iniciales de la suite nueva fallaron en2tests por el conteo de lecturas
estáticas/calldata; logs conservados, auditor corregido, entradas intactas.
Informe final reproducido exactamente;18manifiestos previos/377blobs originales
intactos;106workflows deshabilitados/0activos. Rust/Solidity sin cambios/no ejecutados.

## Siguiente incremento técnico

Antes de otra expansión sin objetivo económico: preparar y ejecutar validación
offline del account/paymaster de ventana con versión/configuración fijada de un
bundler compatible. Usar fuentes ya investigadas en sponsor-window y route-admission;
no dar por ejecutado Rundler porque se leyó su fuente. Registrar reglas completas,
admisión/rechazo, stake y presupuesto necesarios, límites de validez, código/hash
exactos. No eliminar restricciones para forzar PASS ni confundir admisión local
con aceptación comercial del proveedor. Publicar incremento y resultados negativos.
Si falta binario/build/entorno, completar preparación y registrar bloqueo preciso.

No hace falta un candidato nuevo para esa prueba de admisión. Sí hace falta para
medir ruta/margen prospectivos. Una contraparte real financiada y términos sin recurso
no pueden sustituirse por mocks o código. No crear cuentas, contactar proveedores,
firmar, pagar ni enviar sin una instrucción nueva que autorice esas acciones.

## Índice real: NO actualizado por este incremento

Fuente:
`migration/robinhood-registry-recovery-20261016T1507/evidence/pilot/registry.json`.
Raíz`c415105959ea642599deccd7ce690b38325e7480351c5082bda4c03d8cd52643`.
SHAarchivo`e586db0dff1feaeddcfc12e95f30b1ca2bda6a09bb50a5043f58012c497c4382`.
Prefijo87446281–90178727;2732447bloques/158Borrow/56cuentas. Próxima cola90178728;
historia posterior por ampliar87046281–87446280. Revalidar canon y nuevo anchor.
Usar capacity_registry/tail/merge de PR22:256bloques con eventos acumulados,
128por segmento/respuesta,512logs,64cuentas. No volver al registry antiguo limitado128.
PR22muestra histórica16/oct15:17–15:18UTC:47deudores/nueve sin deuda;
cobertura26.6934174575%,falta73.3065825425%;0candidatos SOLO en tres hashes.
No se midieron nuevos candidatos, cobertura, latencia ni oportunidad en esta auditoría.

## Reproducción y restricciones

Worktree `/workspace/scratch/833721a2e367/nqc-zero-principal`, Python3.12.14.
PYTHONDONTWRITEBYTECODE=1; dependencias previas vía
PYTHONPATH=/workspace/scratch/f9e56e91df85/nqc-http-deps. Sin dependencias/APIs nuevas.

```sh
python -m unittest discover -s migration/robinhood-zero-principal-20261016T1533 -p 'test_*.py' -v
python migration/robinhood-zero-principal-20261016T1533/principal_audit.py --out /tmp/nqc-principal-audit.json
python -m unittest discover -s migration/robinhood-real-state-replay-20261016 -p 'test_*.py' -v
python -m unittest discover -s migration/robinhood-sponsor-window-20261016 -p 'test_*.py' -v
python -m unittest discover -s migration/robinhood-opportunity-economics-20261016 -p 'test_*.py' -v
python -m unittest discover -s migration -p test_isolation.py -v
python migration/verify_isolation.py
python migration/engine-v2-20261015/verify_import.py
```

El auditor rechaza sobrescritura de --out. No modificar entradas/políticas/locks
registrados ni relanzar capturas terminadas. Nueva medición requiere publicar nuevo
protocolo ANTES: máximo global512RPC/900s con preparación/esperas, gate350ms entre
inicios compartido por todas las fases. Endpoint único
https://docs-demo.robinhood-mainnet.quiknode.pro/. TLS/proxy/no_proxy/CA/límites intactos;
sin retries, redirects, HTTP paralelo, rescate o cambio de proveedor ante denegación.
Cualquier error detiene todos los RPC y conserva prefijo/cuerpo. Sin trading, firmas,
transacciones, claves, gastos, suscripciones, despliegues; no nexus-engine/Cano/clientes/
dominios. No fusionar. El objetivo comercial no se completa al cerrar este lote.

La tarea existente estaba pausada al último relevo y no se ha interpretado como
fallo ni se ha reactivado. Conservar estado/cadencia; no duplicar tareas ni afirmar
funcionamiento futuro garantizado.
