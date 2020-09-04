"Artefactos de distribución de PyPI /etc."

from dued import artefacto, Coleccion


@artefacto(nombre="all", default=True)
def all_(c):
    "Fabrica todos los paquetes de Python."
    pass


@artefacto
def sdist(c):
    "Construye tar.gz de estilo clásico."
    pass


@artefacto
def wheel(c):
    "Construye una distb. wheel (rueda)."
    pass
