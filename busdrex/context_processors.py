"""
==============================================================================
BusDrex - Procesador de Contexto para Plantillas (context_processors.py)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
==============================================================================
Inyecta en todas las plantillas Django la información institucional del estudiante
y la plataforma, garantizando que el pie de página (footer) se genere de forma
dinámica y centralizada desde la configuración, sin cadenas fijas en el HTML.
"""

from django.conf import settings


def evaluacion_context(request):
    """
    Retorna variables globales de evaluación para renderizado en templates.
    """
    return {
        'METADATA_EVALUACION': getattr(settings, 'METADATA_EVALUACION', {}),
        'FOOTER_TEXT': getattr(
            settings,
            'METADATA_EVALUACION',
            {}
        ).get('FOOTER', 'BusDrex © 2026 | Benjamin Gómez | Sección AP-N4-C1'),
        'STUDENT_NAME': getattr(settings, 'METADATA_EVALUACION', {}).get('ESTUDIANTE', 'Benjamin Gómez'),
        'STUDENT_SECTION': getattr(settings, 'METADATA_EVALUACION', {}).get('SECCION', 'AP-N4-C1'),
        'STUDENT_YEAR': getattr(settings, 'METADATA_EVALUACION', {}).get('AÑO', '2026'),
    }
