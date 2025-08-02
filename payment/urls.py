from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path('currencies/', views.AvailableCurrenciesAPIView.as_view(), name='api_currencies'),
    path('estimate/', views.EstimateAPIView.as_view(), name='api_estimate'),
    path('payments/', views.PaymentListAPIView.as_view(), name='api_payment_list'),
    path('payments/create/', views.PaymentCreateAPIView.as_view(), name='api_payment_create'),
    path('payments/<uuid:id>/', views.PaymentDetailAPIView.as_view(), name='api_payment_detail'),
    path('payments/<uuid:payment_id>/refresh/', views.PaymentStatusUpdateAPIView.as_view(), name='api_payment_refresh'),
    path('payments/ipn/', views.PaymentIPNAPIView.as_view(), name='api_payment_ipn'),
]
