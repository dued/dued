"""
Punto de entrada 'binario' propio de Dued.

Prueba internamente el módulo `programa`.
"""

from . import __version__, Programa

programa = Programa(
    nombre="Dued",
    binario="du[ed]",
    nombres_binarios=["dued", "du"],
    version=__version__,
)
