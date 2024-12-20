# core/middleware.py
from django.http import JsonResponse
from django.utils import timezone
from core.models import License, Barbershop
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth.models import User
import jwt
from django.conf import settings

class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rutas exentas de verificación
        exempt_paths = [
            '/admin',
            '/api/auth/',
            '/api/license/activate/'
        ]
        
        if any(request.path.startswith(path) for path in exempt_paths):
            return self.get_response(request)

        # Solo verificar rutas API
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        try:
            # Obtener y validar el token
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return JsonResponse({
                    'error': 'Token de autorización no proporcionado',
                    'code': 'NO_TOKEN',
                    'show_support': True,
                    'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                }, status=401)

            token = auth_header.split(' ')[1]
            
            try:
                # Decodificar el token
                decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                user_id = decoded_token.get('user_id')
                user = User.objects.get(id=user_id)
                
                # Obtener la barbería y su licencia
                barbershop = Barbershop.objects.filter(owner=user).first()
                if not barbershop or not barbershop.license:
                    return JsonResponse({
                        'error': 'No hay licencia asociada a esta barbería',
                        'code': 'NO_LICENSE',
                        'show_support': True,
                        'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                    }, status=403)

                license = barbershop.license

                # Validar el estado de la licencia
                if not license.is_active:
                    return JsonResponse({
                        'error': 'La licencia no está activa',
                        'code': 'INACTIVE_LICENSE',
                        'show_support': True,
                        'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                    }, status=403)

                # Validar la fecha de expiración
                if license.expires_at < timezone.now():
                    license.is_active = False
                    license.save()
                    return JsonResponse({
                        'error': 'La licencia ha expirado',
                        'code': 'EXPIRED_LICENSE',
                        'show_support': True,
                        'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                    }, status=403)

                # Validar machine_id
                machine_id = request.headers.get('X-Machine-ID')
                if not machine_id:
                    return JsonResponse({
                        'error': 'Identificador de máquina no proporcionado',
                        'code': 'NO_MACHINE_ID',
                        'show_support': True,
                        'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                    }, status=403)

                if license.machine_id != machine_id:
                    return JsonResponse({
                        'error': 'La licencia no está autorizada para esta máquina',
                        'code': 'INVALID_MACHINE',
                        'show_support': True,
                        'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                    }, status=403)

                return self.get_response(request)

            except jwt.ExpiredSignatureError:
                return JsonResponse({
                    'error': 'Token expirado',
                    'code': 'TOKEN_EXPIRED'
                }, status=401)
            except jwt.InvalidTokenError:
                return JsonResponse({
                    'error': 'Token inválido',
                    'code': 'INVALID_TOKEN'
                }, status=401)
            except User.DoesNotExist:
                return JsonResponse({
                    'error': 'Usuario no encontrado',
                    'code': 'USER_NOT_FOUND'
                }, status=404)

        except Exception as e:
            print(f"Error en LicenseMiddleware: {str(e)}")
            return JsonResponse({
                'error': 'Error interno del servidor',
                'code': 'SERVER_ERROR'
            }, status=500)

        return self.get_response(request)