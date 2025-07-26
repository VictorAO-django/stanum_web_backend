# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router and register viewsets
router = DefaultRouter()
router.register(r'profiles', views.UserProfileViewSet, basename='userprofile')
router.register(r'accounts', views.TradingAccountViewSet, basename='tradingaccount')
router.register(r'trades', views.TradeViewSet, basename='trade')
router.register(r'activities', views.AccountActivityViewSet, basename='accountactivity')

urlpatterns = [
    # ViewSet URLs
    path('api/v1/', include(router.urls)),
    
    # Custom API Views
    path('api/v1/dashboard/', views.DashboardAPIView.as_view(), name='dashboard'),
    path('api/v1/admin/dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('api/v1/metaapi/status/', views.MetaAPIServiceStatusView.as_view(), name='metaapi-status'),
]