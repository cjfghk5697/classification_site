#/djangoProject/url.py
from django.contrib import admin
from django.urls import path
from product.views import ProductListAPI
from django.conf.urls.static import static
from django.conf import settings
from django.conf.urls import url, include
from rest_framework import routers
from product import views

router = routers.DefaultRouter()
router.register(r'products', views.ProductListAPI)

urlpatterns = [
    url(r'^', include(router.urls)),
    path('admin/', admin.site.urls),
    path('predict/',include('product.urls')),
	url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)