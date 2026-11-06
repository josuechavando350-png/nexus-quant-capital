# SUPERHUNTER — permisos por remitente real en una EVM local

Esta entrega añade una tercera familia de regresión EVM, distinta de las
transferencias aritméticas y la pausa: autorización de un administrador.
El contrato `AccessLedger` se construye desde fuente Solidity PROPIA mediante
`solc 0.8.30`, se despliega mediante el constructor de Geth EVM y recibe llamadas
con **dos remitentes fijos**. El contrato seguro exige
`require(msg.sender == admin)`; la mutación conocida elimina exactamente esa
línea. No se ejecuta un objetivo externo y ninguna salida constituye un bounty.

## Flujo conectado

Fuente propia → compilación oficial fijada en dos configuraciones → constructor
real → identidad `msg.sender` fija (admin/guest) → varias llamadas acumulativas →
estado persistente real → contraste con referencia aritmética → bitácora DIABLO
→ replay con los mismos motores. Cada caso inicia de un constructor propio;
las reversiones y agotamientos no pueden contarse como cambios confirmados.

La identidad de `admin` procede del constructor, no de una asignación a mano en
el JSON. Se valida mediante almacenamiento empacado (address + uint16 + uint16)
y se exige que el runtime provenga del constructor compilado. En pruebas de
regresión se comprueba además que la nueva selección de remitente solo admite
las dos identidades sintéticas; no existe API de ejecución arbitraria.

## Comandos de laboratorio (sin RPC)

```bash
python3 -m superhunter run-owned-access-lab \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/evm \
  --source-digest SHA256_ACTUAL_DEL_SNAPSHOT_DE_QA \
  --out /ruta/privada/nueva

python3 -m superhunter verify-owned-access-lab \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/evm \
  --source-digest MISMO_SHA256_ACTUAL \
  --bundle /ruta/privada/nueva
```

`run-owned-access-lab` crea salida nueva, privada y autocontenida. El verificador
recompila y reejecuta: una alteración de `execution.json` junto con un hash
actualizado no puede pasar porque contradice el estado observado nuevamente.
El campo `source-digest` debe coincidir con el código actual. La marca
`vulnerability_confirmed` siempre es falsa.

## Límite exacto

Dos direcciones **de laboratorio**; cuatro secuencias fijas de cuatro llamadas;
dos variantes propias, dos perfiles del mismo compilador, una EVM Geth fijada.
La variante incorrecta es conocida de antemano. Los saldos son contadores internos,
NO fondos transferibles. No hay terceros, red, firmas, tokens ni daño económico.
El contraste entre configuraciones NO equivale a dos compiladores ni dos EVMs.
Este perfil no representa toda la semántica de `delegatecall`, proxies,
permisos delegados ni acceso multiusuario arbitrario; tampoco demuestra
que SUPERHUNTER encuentre fallos nuevos en programas externos.

El inventario histórico 27/50/25 permanece sin promociones de completitud.
