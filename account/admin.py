from django.contrib import admin
from .models import *

class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'email_verified', 'is_staff')

admin.site.register(User, UserAdmin)
admin.site.register(OTP)
admin.site.register(CustomAuthToken)
# Register your models here.
