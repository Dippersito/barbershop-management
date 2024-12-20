# core/middleware.py
from django.http import JsonResponse
from core.models import License

class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rutas exentas
        if request.path.startswith('/admin') or \
           request.path.startswith('/api/auth/') or \
           request.path.startswith('/api/license/activate/'):
            return self.get_response(request)

        # Para rutas API que requieren verificación
        if request.path.startswith('/api/'):
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token_key = auth_header.split(' ')[1]
                if not License.objects.filter(
                    machine_id=request.headers.get('X-Machine-ID'),
                    is_active=True
                ).exists():
                    return JsonResponse({
                        'error': 'No existe una licencia activa para esta máquina',
                        'code': 'INVALID_LICENSE'
                    }, status=403)
                return self.get_response(request)

            machine_id = request.headers.get('X-Machine-ID')
            if not machine_id:
                return JsonResponse({'error': 'Machine ID not provided'}, status=403)

            try:
                license = License.objects.get(machine_id=machine_id, is_active=True)
                if not license.is_valid():
                    license.is_active = False
                    license.save()
                    return JsonResponse({'error': 'Invalid or expired license'}, status=403)
                return self.get_response(request)
            except License.DoesNotExist:
                return JsonResponse({'error': 'License not found'}, status=403)

        return self.get_response(request)