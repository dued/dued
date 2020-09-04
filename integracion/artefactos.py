"""
Módulo de Artefactos para uso dentro de las pruebas de integración. 
"""

from dued import artefacto


@artefacto
def imprimir_foo(c):
    print("foo")


@artefacto
def imprimir_nombre(c, nombre):
    print(nombre)


@artefacto
def imprimir_config(c):
    print(c.foo)
