from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path('crypto/currencies/', views.AvailableCurrenciesAPIView.as_view(), name='api_currencies'),
    path('crypto/currencies/full', views.AvailableFullCurrenciesAPIView.as_view()),
    path('crypto/estimate/', views.EstimateAPIView.as_view(), name='api_estimate'),
    path('crypto/payments/', views.PaymentListAPIView.as_view(), name='api_payment_list'),
    path('crypto/create/', views.PaymentCreateAPIView.as_view(), name='api_payment_create'),
    path('crypto/<uuid:id>/', views.PaymentDetailAPIView.as_view(), name='api_payment_detail'),
    path('crypto/<uuid:payment_id>/refresh/', views.PaymentStatusUpdateAPIView.as_view(), name='api_payment_refresh'),
    path('crypto/ipn/', views.PaymentIPNAPIView.as_view(), name='api_payment_ipn'),
    path('crypto/ipn/contest/', views.ContestPaymentIPNAPIView.as_view(), name='api_context_payment_ipn'),

    path('paystack/create/', views.PaystackPaymentView.as_view(), name='create_transaction'),
    path('paystack/verify/<str:reference>/', views.PaystackVerificationView.as_view(), name='verify_transaction'),
    
    # Webhook
    path('paystack/webhook', views.PaystackWebhookView.as_view(), name='paystack_webhook'),

    path('wallet', views.PropFirmWalletView.as_view()),
    path('wallet/transactions/<str:login>', views.PropFirmWalletTransactionView.as_view()),
    path('wallet/withdraw', views.WithdrawView.as_view()),
    path('wallet/fund', views.WalletFundingAPIView.as_view()),
    path('wallet/fund/ipn', views.WalletFundingIPNAPIView.as_view()),
    path('wallet/fund/verify', views.ConfirmTransactionSuccess.as_view()),
]
