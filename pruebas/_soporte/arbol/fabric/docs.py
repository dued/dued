"Artefactos para gestion de doc Sphinx."

from dued import artefacto, Coleccion


@artefacto(nombre="all", default=True)
def all_(c):
    "Fabrica todo formatos de docs."
    pass


@artefacto
def html(c):
    "Genera solo salida HTML."
    pass


@artefacto
def pdf(c):
    "Genere solo salida PDF."
    pass
