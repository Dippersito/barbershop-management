from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def root_view(request):
    return HttpResponse("Barbershop Management API v1.0")

urlpatterns = [
    path('', root_view, name='root'), 
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]
