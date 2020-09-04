from dued import cartefacto, Coleccion


@cartefacto
def go(c):
    c.correr("false")  # Ensures a kaboom if mocking fails


hng = Coleccion(go)
hng.configurar({"correr": {"echo": True}})
