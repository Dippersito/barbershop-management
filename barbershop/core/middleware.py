# core/middleware.py
from django.http import JsonResponse
from core.models import License

class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Permitir rutas del admin
        if request.path.startswith('/admin'):
            return self.get_response(request)

        # Permitir rutas de autenticación
        if request.path.startswith(('/api/auth/', '/api/license/activate/')):
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
                # Aquí es donde verificamos si la licencia existe pero está asociada a otra máquina
                try:
                    # Intentamos encontrar la licencia por machine_id nulo (no activada)
                    license = License.objects.get(machine_id=None, is_active=True)
                    # Si encontramos una, significa que es una licencia disponible
                    license.machine_id = machine_id
                    license.save()
                    return self.get_response(request)
                except License.DoesNotExist:
                    return JsonResponse({'error': 'License not found'}, status=403)
                
        exempt_paths = [
            '/admin',
            '/api/auth/',
            '/api/license/activate/',
            '/api/haircuts/report/',  # Añadir esta ruta
        ]

        # Verificar si la ruta está exenta
        for path in exempt_paths:
            if request.path.startswith(path):
                return self.get_response(request)

        return self.get_response(request)