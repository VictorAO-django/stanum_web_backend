from rest_framework import serializers
from .models import *
from utils.helper import *
from drf_writable_nested.serializers import WritableNestedModelSerializer

class RegistrationSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={"input_type":"password"}, write_only=True)
    class Meta:
        model = User
        fields = ["email", "full_name", "date_of_birth", "phone_number", "country", "password", "password2"]
        extra_kwargs = {
            "password" : {"write_only": True}
        }

    def validate_first_name(self, value):
        # Check if the username starts with "admin"
        if not has_no_special_character(value):
            raise serializers.ValidationError("Firstname must only contain letters and numbers, without special characters.")
        return value
    
    def validate_last_name(self, value):
        # Check if the username starts with "admin"
        if not has_no_special_character(value):
            raise serializers.ValidationError("Lastname must only contain letters and numbers, without special characters.")
        return value
    
    def save(self, *args, **kwargs):
        password1 = self.validated_data["password"]
        password2 = self.validated_data["password2"]
        
        if password1 != password2: #check if password correlate
            raise serializers.ValidationError("Password and confirm Password does not match")

        self.validated_data.pop('password2')
        user = super().save(*args, **kwargs)
        user.set_password(password1)
        user.save()
        return user
    

    
class PasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only = True)
    new_password = serializers.CharField(write_only = True)


class LoginHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginHistory
        fields = ['action', 'status', 'ip_address', 'browser', 'timestamp']


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'home_address', 'town', 'state', 'zip_code',
            'home_address2', 'town2', 'state2', 'zip_code2',
        ]
        depth=1

class UserDataSerializer(WritableNestedModelSerializer):
    address = AddressSerializer()
    class Meta:
        model = User
        fields = ['email', 'phone_number', 'date_of_birth', 'full_name', 'country', 'address']
        read_only_fields = ['email']
    
    def validate_full_name(self, value):
        value = value.strip()  # remove extra spaces
        if not value:
            raise serializers.ValidationError("Full name cannot be blank.")
        return value
    
    def update(self, instance, validated_data):
        request_data = self.context['request'].data
        print("VALIDATED DATA:", request_data)
        return super().update(instance, validated_data)