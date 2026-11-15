"""Sistema de gestion y analisis de una aerolinea (Proyecto 6).

Capas:
    config, conexion        -> acceso a MySQL (Singleton)
    repositorios            -> SQL encapsulado, devuelve DataFrames (Repository)
    modelos                 -> objetos del dominio (dataclasses)
    patrones/               -> State, Observer, Strategy, Builder
    servicios               -> casos de uso que combinan repositorios y patrones
    analisis, graficos      -> analisis con pandas y visualizacion
"""
