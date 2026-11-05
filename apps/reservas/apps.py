from django.apps import AppConfig

class ReservasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reservas'
    verbose_name = 'Reservas, Carro y Ventas de Pasajes'

    def ready(self):
        # Conecta los receptores de señales para el control de stock y liberación automática
        import reservas.signals
