# core/middleware.py
from django.http import JsonResponse
from core.models import License

class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Lista de rutas exentas
        exempt_paths = [
            '/admin',
            '/static/',
            '/api/auth/',
            '/api/license/activate/',
            '/api/haircuts/report/',
        ]

        # Verificar primero si la ruta está exenta
        for path in exempt_paths:
            if request.path.startswith(path):
                return self.get_response(request)

        # Para rutas API protegidas
        if request.path.startswith('/api/'):
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                return self.get_response(request)
            
            machine_id = request.headers.get('X-Machine-ID')
            if not machine_id:
                return JsonResponse({'error': 'Machine ID not provided'}, status=403)

            try:
                license = License.objects.get(machine_id=machine_id)
                if not license.is_valid():
                    return JsonResponse({'error': 'Invalid or expired license'}, status=403)
                return self.get_response(request)
            except License.DoesNotExist:
                try:
                    # Intentamos encontrar una licencia disponible
                    license = License.objects.get(machine_id=None, is_active=True)
                    # Activar la licencia para esta máquina
                    license.machine_id = machine_id
                    license.save()
                    return self.get_response(request)
                except License.DoesNotExist:
                    return JsonResponse({'error': 'License not found'}, status=403)

        # Para cualquier otra ruta
        return self.get_response(request)