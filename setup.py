#!/usr/bin/env python

# Soporta sólo setuptools, distutils tiene una API divergente y más molesta y
# poca gente carecerá de setuptools.
from setuptools import setup, find_packages
import sys

# Información de la versión... leer sin importar
_locales = {}
with open("dued/_version.py") as fp:
    exec(fp.read(), None, _locales)
version = _locales["__version__"]

# PyYAML envía una base de código Python 2/3 dividida. Desafortunadamente,
# algunas versiones de pip intentan interpretar ambas mitades de PyYAML, 
# produciendo SyntaxErrors. Por lo tanto, excluimos lo que parezca inapropiado
# para el intérprete de instalación.
exclude = ["*.yaml3" if sys.version_info[0] == 2 else "*.yaml2"]

# Frankenstein long_description: version-specific changelog note + README
texto = open("README.md").read()
long_description = """
Para saber qué hay de nuevo en esta versión de dued, por favor vea "el 
registro de cambios".

<http://dued.pe/changelog.html#{}>`_.

{}
""".format(
    version, texto
)


setup(
    name="dued",
    version=version,
    description="Dispositovo universal de economia digital",
    license="BSD",
    long_description=long_description,
    author="cleb",
    author_email="clebaresu@gmail.com",
    url="http://kh.dued.pe",
    packages=find_packages(exclude=exclude),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "dued = dued.main:programa.correr",
            "du = dued.main:programa.correr",
        ]
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX",
        "Operating System :: Unix",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Software Distribution",
        "Topic :: System :: Systems Administration",
    ],
)
