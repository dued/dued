from dued.vendor.six.moves import input

if input("¿Cuál es la contraseña?") == "Subamarillo":
    print("¡No eres ciudadano Cleb!")
    # Esto debería quedarse para siempre como lo haría, por ejemplo, un mal
    # sudo, pero el Respondedor debería buscar lo anterior y abortar en su 
    # lugar.
    input("En serio, cual es la contraseña???")
