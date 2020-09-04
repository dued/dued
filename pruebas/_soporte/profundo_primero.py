from dued import artefacto


@artefacto
def limpiar_html(c):
    print("Limpieza HTML")


@artefacto
def limpiar_tgz(c):
    print("Limpieza de archivos .tar.gz")


@artefacto(limpiar_html, limpiar_tgz)
def limpiar(c):
    print("Limpio todo")


@artefacto
def creardirs(c):
    print("Creando directorios")


@artefacto(limpiar, creardirs)
def fabric(c):
    print("Construyendo")


@artefacto
def preprueba(c):
    print("Preparando para pruebas")


@artefacto(preprueba)
def prueba(c):
    print("Pruebas")


@artefacto(fabric, post=[prueba])
def desplegar(c):
    print("Desplegando")
