from django.contrib import admin
from .models import *

class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'email_verified', 'is_staff')

admin.site.register(User, UserAdmin)
admin.site.register(OTP)
admin.site.register(CustomAuthToken)

admin.site.register(LoginHistory)

admin.site.register(Referral)
admin.site.register(ReferralEarning)
admin.site.register(ReferalEarningTransaction)

admin.site.register(Address)

admin.site.register(DocumentType)
admin.site.register(ProofOfIdentity)
admin.site.register(ProofOfAddress)

admin.site.register(Notification)
admin.site.register(HelpCenter)
admin.site.register(Ticket)
admin.site.register(Message)
# Register your models here.
