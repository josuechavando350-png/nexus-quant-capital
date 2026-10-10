# Realización del residual en ETH: prueba histórica acotada

El residual del escenario Balancer con pago observado se convierte íntegramente
en ETH en una llamada atómica del **harness de operador de investigación**.
Incremento nativo: **240,390,311,727,552 wei**, sin consumir su WETH ni ETH previos.
El préstamo ya queda devuelto y se conserva el pago nativo al receptor del bloque.
Esto prueba el retiro WETH→ETH en ese estado y bajo ese perfil; no acredita una
wallet operativa, financiación inicial del gas, inclusión o beneficio completo.

El archivo `inputs/native-realization.zip` conserva 20 miembros, 227,851 bytes,
SHA-256 `46bdc3d97787154e286a8c210bdfdf07d2faf4788dc0fd8d52dc58357dd0643a`.
Productor padre: `d6fcf7206b82e8e78a6104a89acb699a3c9aa0ad`; los cinco archivos
del productor quedan fijados dentro del archivo y en su informe. Forge y Solc
usan los mismos hashes autenticados en la comparación anterior.

## Alcance de ejecución

El runner sólo acepta el witness anterior de 127 respuestas, por SHA-256.
No implementa adquisición ni fallback: una lectura ausente falla offline.
Las fuentes originales se copian, se aplican los overlays publicados y se
añade una subclase al test Balancer con pago. La clase anterior permanece
íntegra y se ejecutan también sus dos pruebas, sin eliminar aserciones.

Las dos pruebas añadidas comprueban:

- Devolución, pago observado, retiro del WETH residual, incremento nativo exacto
  y preservación de inventario; ejecutor y estrategia no retienen WETH.
- Ante beneficio mínimo imposible, reversión de pagos, préstamo y liquidación,
  saldos previos intactos y ninguna identidad de ejecución consumida.

La función `settleToNative` acepta sólo llamadas del propio contrato de prueba.
Es un harness para comprobar contabilidad/atomicidad; **no es un contrato de
operación ni un mecanismo autenticado de retiro a una wallet**. Los saldos
nativos que asigna o conserva el entorno de pruebas no acreditan gas del usuario.
No se firmó, transmitió ni desplegó en una cadena real.

Las cuatro pruebas pasan en modos normal y aislado. El replay no abre upstream;
254 respuestas servidas se vinculan al witness. El consumidor verifica todos
los miembros, fuentes, overlays, logs, métricas y la igualdad con el witness
archivado anterior. Pasan 27 controles Python afectados y 9 de aislamiento.
Los 637 objetos originales permanecen verificados; cero workflows activos.
Rust no cambió ni se repitieron sus pruebas.

El primer reintento local de aislamiento dejó un log truncado durante la
presión de disco; se conserva separado y no cuenta como aprobado. Se comprimió
sin pérdidas la copia extraída de 4,301 chunks primarios, comprobando todos sus
hashes antes de liberar esa copia. El reintento posterior sí pasa las 9 pruebas.
El archivo fuente exacto queda conservado; no se modifica evidencia para ahorrar
espacio ni se excluyen archivos de los controles de aislamiento.

## Costes aún parciales

| Perfil | Gas medido de la llamada | Intrínseco 4/16 del calldata | Suma ilustrativa |
| --- | ---: | ---: | ---: |
| Normal | 552,742 | 27,060 | 579,802 |
| Aislado | 532,120 | 27,060 | 559,180 |

Al aplicar la base fee histórica (59,451,728 wei/gas), quedan
205,920,080,929,696 / 207,146,094,464,512 wei **para todos los demás costes**.
A 1 gwei, ambos residuos son negativos: −339,411,688,272,448 /
−318,789,688,272,448 wei. No son utilidades netas ni una cotización de producción.
Las métricas incluyen comprobaciones del harness y conservan diferencias entre
modos, el perfil Cancun y estado del bloque anterior con sólo avance temporal.
Faltan costes y reglas operativas completas, autorización de wallet/gas,
despliegue/amortización, fallos, competencia y recepción antes de decidir.
El saldo convertido no autoriza reinversión automática bajo la política vigente.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/verify_native.py \
  --archive migration/census_v2/execution_replay/inputs/native-realization.zip \
  --output /tmp/native-realization-readback.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2/execution_replay -p 'test_*.py'
```

`native-validation/report.json` registra límites y aritmética entera.
`complete_profit_wei=null`, admisión económica y cierre siguen sin acreditar.
Este único caso retrospectivo no demuestra capacidad comercial del universo.
