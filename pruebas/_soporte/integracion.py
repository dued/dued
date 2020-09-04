"""
Un accesorio de estilo semi-integración-prueba que abarca múltiples ejemplos 
de funciones.

Sin embargo, si somos honestos, el nuevo paquete de accesorios 'arbol' es 
mucho más grande.
"""

from dued.artefactos import artefacto


@artefacto
def imprimir_foo(c):
    print("foo")


@artefacto
def imprimir_nombre(c, nombre):
    print(nombre)


@artefacto
def imprimir_arg_con_guionbajo(c, mi_opcion):
    print(mi_opcion)


@artefacto
def foo(c):
    print("foo")


@artefacto(foo)
def bar(c):
    print("bar")


@artefacto
def post2(c):
    print("post2")


@artefacto(post=[post2])
def post1(c):
    print("post1")


@artefacto(foo, bar, post=[post1, post2])
def biz(c):
    print("biz")


@artefacto(bar, foo, post=[post2, post1])
def boz(c):
    print("boz")
