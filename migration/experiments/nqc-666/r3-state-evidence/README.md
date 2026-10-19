# NQC666 R3 — pruebas de estado e invalidación

Verificador experimental offline de pruebas EIP-1186 relativas a un encabezado fijado,
con reutilización de nodos dentro del paquete, gateway secuencial y cálculo condicional
en Rust R1. No certifica consenso, ejecución de oráculo, financiación ni admisión comercial.

- [Diseño y fronteras de confianza](DESIGN.md)
- [Contrato de medición](PRE_REGISTER.md)
- [Resultados y limitaciones](REPORT.md)
- [Procedencia e inventario acotado](PROVENANCE.json)
- [Manifiesto SHA-256](MANIFEST.sha256)

## Requisitos

Python 3.12 y las versiones de `requirements.lock`, Rust 1.90.0 y solc 0.8.19.
Son los componentes ya disponibles en el entorno de R1. Los scripts no instalan
paquetes, no descargan código y no acceden a RPC. La instalación de dependencias
en otra máquina es una preparación separada; no hay servicios de pago.

## Reproducir

Desde este directorio, con el entorno Python correspondiente activo y Rust en PATH:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/reproduce.py \
  --out /tmp/nqc666-r3-run --solc /ruta/solc-0.8.19
```

La salida debe ser nueva y estar fuera del repositorio. Compila R1 sin modificarlo,
ejecuta sus pruebas y las del motor base, aislamiento, regeneración exacta de fixtures,
pruebas Python, contraste Solidity de slots y las 12 corridas de benchmark.
Conserva logs, hashes, versiones, muestras crudas y percentiles. La frecuencia y carga
del host afectan las mediciones; reproducibilidad no significa nanosegundos idénticos.

Para verificar los resultados entregados sin repetir el benchmark:

```sh
sha256sum -c MANIFEST.sha256
PYTHONDONTWRITEBYTECODE=1 python scripts/verify.py
```

Para correr solamente las pruebas del nuevo adaptador, con el ejecutable R1 compilado:

```sh
NQC_R1_EVAL=/ruta/al/target/release/eval PYTHONDONTWRITEBYTECODE=1 \
  python -m unittest discover -s tests -v
```

Ese ejecutable es obligatorio: la prueba de integración falla si no se proporciona;
no se omite silenciosamente. `fixtures/synthetic-index.json` contiene políticas de
laboratorio explícitas. No deben usarse como configuración de una cadena real.

`state_evidence.verify(bytes, policy, now_s, shared=True)` devuelve hechos relativos
a raíz o lanza `Rejected`. `shared=False` ejecuta el control equivalente sin reutilizar
decodificaciones. Para manejo de eventos use `Gateway`, que revoca el snapshot previo
antes de procesar cada actualización y exige tickets vigentes.

No existe un comando para operar, firmar, desplegar o enviar transacciones. El trabajo
comercial de NQC031/032 permanece fuera del alcance de esta revisión.
