# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

urlpatterns = [
    # ViewSet URLs
    # path('api/v1/', include(router.urls)),
    
    # # Custom API Views
    # path('api/v1/dashboard/', views.DashboardAPIView.as_view(), name='dashboard'),
    # path('api/v1/admin/dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    # path('api/v1/metaapi/status/', views.MetaAPIServiceStatusView.as_view(), name='metaapi-status'),

    path('accounts', TradingAccountView.as_view()),
]