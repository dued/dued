from dued import artefacto, Coleccion


@artefacto
def z_altonivel(c):
    pass


@artefacto
def subartefacto(c):
    pass


hng = Coleccion(z_altonivel, Coleccion("a", Coleccion("b", subartefacto)))
