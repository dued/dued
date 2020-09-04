"""
LETRAS EXPLICITAS
"""

from dued import artefacto, Coleccion


@artefacto(alias=["otro_alto"])
def alto_nivel(c):
    pass


@artefacto(alias=["otro_sub"], default=True)
def sub_artefacto(c):
    pass


sub = Coleccion("sub_nivel", sub_artefacto)
hng = Coleccion(alto_nivel, sub)
