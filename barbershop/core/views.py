# core/views.py
from rest_framework import viewsets, status, serializers
from django.db import models
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.db.models import Sum, Count, Q
from .models import License, Barbershop, Barber, Haircut, Reservation
from .serializers import (
    LicenseSerializer, BarbershopSerializer, BarberSerializer,
    HaircutSerializer, ReservationSerializer
)
from rest_framework_simplejwt.views import TokenObtainPairView
from django.http import HttpResponse
import io
import traceback
from django.shortcuts import render
from rest_framework.decorators import action
from rest_framework.renderers import TemplateHTMLRenderer
from django.db import transaction
from django.contrib.auth.models import User


# Vista para activar licencias
class LicenseActivationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            license_key = request.data.get('license_key')
            machine_id = request.data.get('machine_id')
            print(f"License activation attempt - Key: {license_key}, Machine ID: {machine_id}")

            if not all([license_key, machine_id]):
                return Response({
                    'error': 'Se requiere license_key y machine_id',
                    'show_support': True,
                    'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                }, status=status.HTTP_400_BAD_REQUEST)

            existing_license = License.objects.filter(
                machine_id=machine_id,
                is_active=True,
                expires_at__gt=timezone.now()
            ).first()

            if existing_license:
                if str(existing_license.key) == str(license_key):
                    return Response({
                        'message': 'Esta licencia ya está activada para esta máquina',
                        'status': 'active'
                    })
                return Response({
                    'error': 'Esta máquina ya tiene una licencia activa diferente',
                    'show_support': True,
                    'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                }, status=status.HTTP_400_BAD_REQUEST)

            license = License.objects.filter(key=license_key).first()
            if not license:
                return Response({
                    'error': 'Licencia no encontrada',
                    'show_support': True,
                    'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                }, status=status.HTTP_404_NOT_FOUND)

            if license.expires_at < timezone.now():
                return Response({
                    'error': 'Esta licencia ha expirado',
                    'show_support': True,
                    'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                }, status=status.HTTP_400_BAD_REQUEST)

            if license.machine_id and license.machine_id != machine_id:
                return Response({
                    'error': 'Esta licencia ya está en uso en otra máquina',
                    'show_support': True,
                    'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                }, status=status.HTTP_400_BAD_REQUEST)

            license.machine_id = machine_id
            license.activated_at = timezone.now()
            license.save()

            return Response({'message': 'Licencia activada exitosamente', 'status': 'activated'})

        except Exception as e:
            print(f"License activation error: {str(e)}")
            return Response({
                'error': 'Error al activar la licencia',
                'show_support': True,
                'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
# Vista para gestionar barberos
class BarberViewSet(viewsets.ModelViewSet):
    serializer_class = BarberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Barber.objects.filter(barbershop__owner=self.request.user)

    def perform_create(self, serializer):
        try:
            barbershop = Barbershop.objects.get(owner=self.request.user)
            serializer.save(barbershop=barbershop)
        except Barbershop.DoesNotExist:
            raise serializers.ValidationError(
                {"error": "No se encontró una barbería asociada a este usuario. Por favor, contacte al administrador."}
            )

# Vista para gestionar cortes de cabello
class HaircutViewSet(viewsets.ModelViewSet):
    serializer_class = HaircutSerializer
    permission_classes = [IsAuthenticated]
    queryset = Haircut.objects.all()

    def get_queryset(self):
        return Haircut.objects.filter(barbershop__owner=self.request.user)

    def perform_create(self, serializer):
        barbershop = Barbershop.objects.get(owner=self.request.user)
        serializer.save(barbershop=barbershop)

    @action(detail=False, methods=['get'])
    def balance(self, request):
        today = timezone.now().date()
        period = request.query_params.get('period', 'daily')
        
        if period == 'daily':
            haircuts = self.get_queryset().filter(created_at__date=today)
        else:  # monthly
            month_start = today.replace(day=1)
            haircuts = self.get_queryset().filter(
                created_at__date__gte=month_start,
                created_at__date__lte=today
            )

        totals = {
            'totalIncome': sum(h.amount for h in haircuts),
            'totalCuts': haircuts.count(),
            'cashTotal': sum(h.amount for h in haircuts if h.payment_method == 'CASH'),
            'yapeTotal': sum(h.amount for h in haircuts if h.payment_method == 'YAPE')
        }

        return Response({
            f'{period}Stats': totals
        })

    @action(detail=False, methods=['get'])
    def report(self, request):
        print("Recibiendo solicitud de reporte")
        print(f"Usuario autenticado: {request.user}")
        print(f"Headers: {request.headers}")
        
        try:
            if not request.user.is_authenticated:
                print("Usuario no autenticado")
                return Response(
                    {'error': 'No autorizado'}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )

            start_date = request.query_params.get('startDate')
            end_date = request.query_params.get('endDate')
            
            print(f"Fechas: {start_date} - {end_date}")
            
            haircuts = self.get_queryset().filter(
                barbershop__owner=request.user,
                created_at__date__range=[start_date, end_date]
            ).order_by('created_at')
            
            print(f"Cortes encontrados: {haircuts.count()}")

            total = haircuts.aggregate(
                total=Sum('amount'),
                total_cash=Sum('amount', filter=Q(payment_method='CASH')),
                total_yape=Sum('amount', filter=Q(payment_method='YAPE'))
            )

            context = {
                'haircuts': haircuts,
                'start_date': start_date,
                'end_date': end_date,
                'total': total['total'] or 0,
                'total_cash': total['total_cash'] or 0,
                'total_yape': total['total_yape'] or 0,
            }

            return render(request, 'core/report.html', context)
            
        except Exception as e:
            print(f"Error en reporte: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['delete'])
    def delete_all(self, request):
        try:
            # Obtener todos los cortes de la barbería actual
            haircuts = self.get_queryset()
            deleted_count = haircuts.count()
            
            if deleted_count == 0:
                return Response({
                    'message': 'No hay registros para eliminar'
                }, status=status.HTTP_200_OK)

            # Eliminar los registros
            haircuts.delete()

            return Response({
                'message': f'Se eliminaron {deleted_count} registros correctamente',
                'deleted_count': deleted_count
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error al eliminar registros: {str(e)}")
            return Response(
                {'error': 'Error al eliminar los registros'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
# Vista para gestionar reservas
class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Reservation.objects.all()

    def get_queryset(self):
        return Reservation.objects.filter(
            barbershop__owner=self.request.user,
            is_active=True
        ).order_by('date', 'time')

    def perform_create(self, serializer):
        try:
            barbershop = Barbershop.objects.get(owner=self.request.user)
            serializer.save(barbershop=barbershop)
        except Barbershop.DoesNotExist:
            raise serializers.ValidationError(
                {"error": "No se encontró una barbería asociada a este usuario"}
            )

    
class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        try:
            machine_id = request.headers.get('X-Machine-ID')
            print(f"Login attempt - User: {request.data.get('username')}, Machine ID: {machine_id}")

            if not machine_id:
                return Response({
                    'error': 'Se requiere ID de máquina',
                    'detail': 'Por favor, active una licencia primero'
                }, status=status.HTTP_400_BAD_REQUEST)

            response = super().post(request, *args, **kwargs)
            
            if response.status_code == 200:
                user = User.objects.get(username=request.data.get('username'))
                
                license = License.objects.filter(
                    machine_id=machine_id,
                    is_active=True,
                    expires_at__gt=timezone.now()
                ).first()

                if not license:
                    return Response({
                        'error': 'No hay licencia válida para esta máquina',
                        'show_support': True,
                        'support_message': 'Para soporte o validar su licencia, contactar con Stephano Cornejo Córdova al 940183490'
                    }, status=status.HTTP_403_FORBIDDEN)

                with transaction.atomic():
                    barbershop = Barbershop.objects.filter(owner=user).first()
                    if barbershop:
                        barbershop.license = license
                        barbershop.save()
                    else:
                        Barbershop.objects.create(
                            name=f'Barbería de {user.username}',
                            owner=user,
                            license=license
                        )

                return response

        except User.DoesNotExist:
            return Response({
                'error': 'Usuario no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Login error: {str(e)}")
            return Response({
                'error': 'Error en el proceso de login',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
