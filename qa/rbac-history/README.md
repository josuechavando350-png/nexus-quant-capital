# Hunter ante una corrección histórica de permisos

Se evaluó el componente de permisos de [esta revisión de Hunter](https://github.com/josuechavando350-png/nexus-quant-capital/commit/05002c36c12a1b572b5d425b7b0714189c448109) con archivos públicos fijados por revisión y SHA-256. Se utilizó la interfaz audit-permissions y se verificó cada expediente en un segundo proceso. No se levantó ningún servicio de terceros.

| Prueba | Resultado |
|---|---|
| Kubernetes, con una regla de mínimo privilegio fijada para todos los roles | Señaló las dos configuraciones con el permiso histórico y aceptó los cuatro controles. |
| Kubernetes, sin declarar reglas | Se abstuvo en los seis casos. Los dos positivos quedaron sin detectar. |
| Casbin v2.100.0 | Coincidió en 24 de 24 decisiones, 12 permisos y 12 denegaciones. Ocho decisiones por cada modelo básico, jerárquico y con denegación explícita. |

El par v1.21.0 y v1.22.0 corresponde a una única corrección en los roles predeterminados para clústeres nuevos. Los casos se derivaron de los manifiestos oficiales para admin, edit y view. Se preservaron por separado las concesiones por verbo y la herencia declarada mediante selectores de etiquetas. La regla solo cubre escrituras sin restricción por nombre en el recurso evaluado. Un clúster actualizado o personalizado puede tener otra política. [Cambio documentado por Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#write-access-for-endpoints)

Casbin proporciona las expectativas de autorización en sus propias pruebas. En el modelo jerárquico se compararon los permisos efectivos esperados para dos sujetos en las cuatro combinaciones de recurso y acción de la política. Cada coincidencia cuenta como una decisión de autorización. [Pruebas oficiales de Casbin](https://github.com/casbin/casbin/blob/c55ed50772950c9b6eb80460fed5b889e0df87fd/model_test.go) · [Prueba de herencia](https://github.com/casbin/casbin/blob/c55ed50772950c9b6eb80460fed5b889e0df87fd/rbac_api_test.go)

El adaptador traduce datos a la representación de Hunter. No ejecuta el código externo. El proceso que analiza permisos recibe únicamente la política, sin las etiquetas de referencia. En la evaluación histórica se usa el protocolo nativo de compromiso, congelación y revelación. La corrección y las respuestas de referencia ya eran públicas. Las predicciones congeladas prueban el orden de puntuación, sin establecer custodia independiente ni capacidad de descubrir fallos desconocidos. La gravedad interna del evaluador solo satisface su esquema.

Para repetir con un checkout limpio del productor indicado y CPython 3.12 con PyYAML, se preparan los nueve archivos y se ejecuta el análisis sin red. La carpeta de evidencias debe ser nueva.

```sh
python3.12 -B benchmark.py /tmp/rbac-datos --fetch-only
unshare --user --map-current-user --net python3.12 -B benchmark.py /tmp/rbac-datos --product /ruta/al/productor --evidence-dir /tmp/rbac-evidencia
```

[Protocolo fijado antes del análisis](protocolo.txt) · [Versiones y huellas](inputs.json) · [Resultados por caso](resultado.json)
