"""
Script de captura-de-regresión barebones que busca fallas efímeras de correr().

Se pretende correr desde el nivel superior del proyecto a través de 
``du regresion``. En un mundo ideal esto sería realmente parte de la suite de
pruebas de integración, pero:

- algo en el entorno externo de dued o pytest parece evitar que tales 
  problemas aparezcan de manera confiable (ver, por ejemplo, el número 660)
- Puede tardar bastante en ejecutarse, incluso en comparación con otras 
  pruebas de integración.
"""


import sys

from dued import artefacto


@artefacto
def chequeo(c):
    conteo = 0
    fallas = []
    for _ in range(0, 1000):
        conteo += 1
        try:
            # 'ls' elegido como un ejemplo arbitrario, lo suficientemente 
            # rápido para hacer un bucle pero que hace algo de trabajo real
            # (donde, por ejemplo, 'sleep' es menos útil)
            respuesta = c.correr("ls", ocultar=True)
            if not respuesta.ok:
                fallas.append(respuesta)
        except Exception as e:
            fallas.append(e)
    if fallas:
        print("correr() FALLÓ {}/{} veces!".format(len(fallas), conteo))
        sys.exit(1)
