# core/views.py
from rest_framework import viewsets, status, serializers
from django.db import models
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.db.models import Sum, Count
from .models import License, Barbershop, Barber, Haircut, Reservation
from .serializers import (
    LicenseSerializer, BarbershopSerializer, BarberSerializer,
    HaircutSerializer, ReservationSerializer
)
from rest_framework_simplejwt.views import TokenObtainPairView
from django.http import HttpResponse
import io
from django.shortcuts import render
from rest_framework.decorators import action
from rest_framework.renderers import TemplateHTMLRenderer
from django.db import transaction


# Vista para activar licencias
class LicenseActivationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        license_key = request.data.get('license_key')
        machine_id = request.data.get('machine_id')

        if not license_key or not machine_id:
            return Response(
                {'error': 'Se requiere license_key y machine_id'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Verificar si ya existe una licencia activa para este machine_id
            existing_license = License.objects.filter(
                machine_id=machine_id,
                is_active=True,
                expires_at__gt=timezone.now()
            ).first()

            if existing_license:
                # Si la licencia existente es la misma que están intentando activar
                if str(existing_license.key) == str(license_key):
                    return Response({'message': 'Esta licencia ya está activada para esta máquina'})
                else:
                    return Response(
                        {'error': 'Esta máquina ya tiene una licencia activa diferente'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Buscar la licencia que intentan activar
            try:
                license = License.objects.get(key=license_key)

                # Verificar si la licencia está vencida
                if license.expires_at < timezone.now():
                    return Response(
                        {'error': 'Esta licencia ha expirado'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Verificar si la licencia ya está siendo usada en otra máquina
                if license.machine_id and license.machine_id != machine_id:
                    return Response(
                        {'error': 'Esta licencia ya está en uso en otra máquina'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Activar la licencia para esta máquina
                license.machine_id = machine_id
                license.activated_at = timezone.now()
                license.save()

                return Response({'message': 'Licencia activada exitosamente'})

            except License.DoesNotExist:
                return Response(
                    {'error': 'Licencia no encontrada'},
                    status=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            return Response(
                {'error': f'Error al activar la licencia: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
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

    @action(detail=False, methods=['get'], renderer_classes=[TemplateHTMLRenderer])
    def report(self, request):
        try:
            start_date = request.query_params.get('startDate')
            end_date = request.query_params.get('endDate')
            
            # Obtener los cortes
            haircuts = self.get_queryset().filter(
                created_at__date__range=[start_date, end_date]
            ).order_by('created_at')

            # Calcular totales
            total = sum(h.amount for h in haircuts)
            total_cash = sum(h.amount for h in haircuts if h.payment_method == 'CASH')
            total_yape = sum(h.amount for h in haircuts if h.payment_method == 'YAPE')

            context = {
                'haircuts': haircuts,
                'start_date': start_date,
                'end_date': end_date,
                'total': total,
                'total_cash': total_cash,
                'total_yape': total_yape,
            }

            # Usar render directamente para la plantilla
            return render(request, 'core/report.html', context)
        except Exception as e:
            print(f"Error generating report: {str(e)}")  # Para debugging
            return Response(
                {'error': 'Error generando el reporte'},
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
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            with transaction.atomic():
                # Obtener el usuario que acaba de iniciar sesión
                user = self.user

                # Verificar si ya tiene una barbería
                barbershop = Barbershop.objects.filter(owner=user).first()
                if not barbershop:
                    # Crear una nueva licencia
                    license = License.objects.create(
                        is_active=True,
                        expires_at=timezone.now() + timezone.timedelta(days=365)
                    )
                    
                    # Crear una nueva barbería
                    barbershop = Barbershop.objects.create(
                        name=f'Barbería de {user.username}',
                        owner=user,
                        license=license
                    )

        return response
    
from django.http import HttpResponse

def test_view(request):
    return HttpResponse("Test view working!")

# En core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ... tus otras URLs ...
    path('test/', views.test_view, name='test'),
]