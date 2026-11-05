# BusDrex - Plataforma de Gestión de Pasajes de Buses Interurbanos
# Módulo principal del proyecto Django

# ------------------------------------------------------------------------------
# COMPATIBILIDAD CON PYMYSQL
# ------------------------------------------------------------------------------
# Permite que Django utilice PyMySQL simulando la interfaz de MySQLdb (mysqlclient).
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
