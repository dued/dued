from dued import Coleccion, artefacto, llamar

from paquete import modulo


@artefacto
def top_pre(c):
    pass


@artefacto(llamar(top_pre))
def altonivel(c):
    pass


hng = Coleccion(modulo, altonivel)
