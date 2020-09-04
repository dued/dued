from dued import artefacto, Coleccion


@artefacto
def altonivel(c):
    pass


@artefacto
def subartefacto(c):
    pass


hng = Coleccion(
    altonivel, Coleccion("a", subartefacto, Coleccion("otracosa", subartefacto))
)
