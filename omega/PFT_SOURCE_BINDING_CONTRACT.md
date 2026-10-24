# H2D: enlace offline de fuente PFT

`pft_source_binding.py` implementa el enlace local descrito en
`migration/IMPORT-PLAN.md`. Produce `OFFLINE_SOURCE_BINDING_PASS`, nunca una
recertificación. No activa ni ejecuta workflows.

## Entradas y verificaciones

- Checkout destino completo, limpio y en el commit exacto indicado por
  `--expected-commit`. Se leen todos los blobs y modos de HEAD; un índice
  `assume-unchanged` no puede ocultar cambios de bytes.
- Checkout original separado en `e259739c9f75fedcd1061d2f78d6b8852e7a3060`.
  Debe contener la historia original completa y los archivos PFT protegidos,
  el materializador y el perfil. Puede ser el checkout NQC sparse del original.
  Requiere `git fsck`, grafo de padres completo, ascendencia PFT original y
  ausencia de drift protegido. Rechaza grafts, replacements e historia shallow.
- Recibo `MATERIALIZATION.json` original obtenido previamente. No es un artifact
  de GitHub Actions: es el recibo local de derivación PFT. El adaptador reproduce
  sus datos con el materializador fijado y compara ambos documentos íntegros.
- Directorio de salida nuevo, fuera de las entradas y de ambos repositorios.
  El materializador original, sin cambios, crea allí una copia efectiva nueva.
  Se vuelven a calcular ambos árboles y a comprobar los checkouts al terminar.

Se preservan IDs de repositorio, commit/tree original, overlays y autoridad
histórica. El nuevo registro incorpora commit/tree del consumidor NQC, hashes
del adaptador, manifest, recibos y logs, más la comprobación de aislamiento
completo. El proceso Git no hereda redirecciones y no permite fetch por protocolo.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 omega/pft_source_binding.py \
  --source-checkout /ruta/checkout-original-nqc \
  --source-receipt /ruta/materializacion-previa/MATERIALIZATION.json \
  --expected-commit <commit-completo-del-checkout-destino> \
  --output /ruta/nueva/pft-binding
```

## Significado del resultado

`binding.json` enlaza contenido local reproducido con un commit limpio exacto.
El nombre/ID del repositorio destino son los fijados por el contrato de importación;
este comando offline no autentica que ese commit esté publicado en GitHub.
`remote_producer_identity_authenticated` es `false`; workflow, run y artifact
son `null`. La publicación y lectura independiente del commit se auditan aparte.

El recibo original conserva su autoridad histórica dentro de
`materialization_receipt`. El registro exterior mantiene todos los permisos y
estados de certificación en `false`. No afirma que la nueva raíz descienda del
commit certificado original. Tampoco convierte esta materialización en prueba
de forks, replay desconectado, rentabilidad o cobertura de mercado.

Una ejecución fallida puede conservar logs o una copia parcial para diagnóstico;
no escribe `binding.json`. No reutilizar ese directorio como una ejecución válida.
Una vez compilada una copia efectiva puede contener archivos adicionales de build;
la reproducción del recibo requiere una copia fresca, antes del build.

El formato heredado se registra tal como dispone
`nqc-protocol-fork-source-binding.yml.disabled`: sus checks `rustfmt`/`forge fmt`
capturan el código de salida con `set +e`. Los builds/tests siguen siendo gates
obligatorios con `set -e`. Un fallo de formato no se presenta como PASS ni autoriza
a reescribir el source recuperado.
