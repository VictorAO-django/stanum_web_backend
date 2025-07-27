"""
URL configuration for vermittlungsbot project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from .views import *
from django.urls import path

urlpatterns = [
    path('auth/login', LoginView.as_view()),
    path('auth/signup', SignupView.as_view()),
    path('auth/otp/resend', ResendOtpView.as_view()),
    path('auth/token/refresh', TokenRefreshView.as_view()),
    path('auth/verify/<int:id>/<str:otp>', AccountVerificationView.as_view()),

    path('auth/password/forget', ForgetPasswordView.as_view()),
    path('auth/password/reset/validate-otp/<int:id>/<int:otp>', PasswordResetOTPValidationView.as_view()),
    path('auth/password/reset/<int:id>/<str:token>', PasswordResetView.as_view()),
]