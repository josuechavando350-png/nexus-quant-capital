# Árboles raíz y manifiestos de los 47 proyectos sin checkout completo

Desde la rama de producto del PR 111, cada uno de los 47 objetos raíz se obtuvo de GitHub con el filtro Git `tree:0` y la revisión de árbol registrada en el PR 114. Cada transferencia de esta verificación contenía un único objeto de tipo árbol. El recibo guarda sus bytes originales. El lector recalcula el identificador Git, valida modos y orden de entradas y contrasta la identidad con los 47 commits de procedencia. Las 153 fuentes completas siguen en sus commits anteriores.

La preparación lee exclusivamente blobs declarativos de nombre fijo en la raíz. La extensión de `query-product` comprueba sus identificadores contra esos árboles y calcula el inventario en la sesión. De 47 proyectos, 29 presentan alguno de los cinco formatos reconocidos. Se verificaron 34 archivos y 1,311 nombres de dependencia contados por archivo. Los otros 18 reciben un inventario vacío con su árbol verificado. El alcance excluye resolución transitiva, ejecución de instaladores, características opcionales activas y conclusiones sobre la seguridad de un paquete. Un mismo nombre puede aparecer en más de un archivo.

```sh
python3.12 -B -m superhunter.tools.fetch_root_manifests /ruta/nueva/manifiestos
python3.12 -B -m superhunter.tools.catalog_session --root-manifests /ruta/nueva/manifiestos \
    /ruta/sesion-preparada root-declarations
```

Las respuestas por nombre incluyen el archivo, el blob Git, su SHA-256 y los nombres declarados. El SHA-256 de las 47 filas canónicas es `57bb32779f611d4187d3a2a2e6ac373ec02c7a6e0c385d5c520eaf48ec8fee94`. La consulta de procedencia por sí sola conserva pendiente la participación funcional del proveedor. [Árboles raíz](product_supply/remote-root-proofs.json) · [Código](product_remote_roots.py) · [Preparar la sesión estándar](CATALOG_SESSION.md)
