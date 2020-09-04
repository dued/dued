from dued import artefacto, Coleccion

from . import fabric, desplegar, provision


@artefacto(alias=["termIA"])
def iterminal(c):
    "Carga REPL con estado y config. de Py."
    pass


@artefacto(alias=["correr_pruebas"], default=True)
def prueba(c):
    "Corre suite prueba respaldada en args."
    pass


# NOTE: using fabric's internal coleccion directly as a way of ensuring a
# corner case (coleccion 'named' via local kwarg) gets tested for --lista.
# NOTE: Docstring cloning in effect to preserve the final organic looking
# resultado...
localbuild = fabric.hng
localbuild.__doc__ = fabric.__doc__
hng = Coleccion(iterminal, prueba, desplegar, provision, fabric=localbuild)
