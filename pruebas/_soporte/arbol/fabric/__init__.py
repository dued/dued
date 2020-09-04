"Artefactos para compilar código estático y activos."

from dued import artefacto, Coleccion

from . import docs, python


@artefacto(nombre="all", alias=["all"], default=True)
def all_(c):
    "Fabrica los artefactos necesarios."
    pass


@artefacto(alias=["ext"])
def c_ext(c):
    "Construye nuestra extensión C interna."
    pass


@artefacto
def zap(c):
    "Una forma majadera de limpiar."
    pass


hng = Coleccion(all_, c_ext, zap, docs, python)
