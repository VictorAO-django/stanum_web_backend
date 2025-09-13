from rest_framework import serializers
from .models import *
from utils.helper import *
from drf_writable_nested.serializers import WritableNestedModelSerializer

class RegistrationSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={"input_type": "password"}, write_only=True)
    home_address = serializers.CharField(write_only=True)
    town = serializers.CharField(write_only=True)
    state = serializers.CharField(write_only=True)
    zip_code = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email", "full_name", "date_of_birth", "phone_number", "country",
            "password", "password2", "home_address", "town", "state", "zip_code"
        ]
        extra_kwargs = {
            "password": {"write_only": True}
        }

    def validate(self, data):
        # Check password match
        if data["password"] != data["password2"]:
            raise serializers.ValidationError({"password": "Passwords do not match"})

        # Ensure full_name has at least 2 parts
        full_name = data.get("full_name", "").strip()
        if len(full_name.split()) < 2:
            raise serializers.ValidationError({"full_name": "Please enter both first and last name as Full name."})

        return data

    def create(self, validated_data):
        # Extract nested fields
        home_address = validated_data.pop("home_address")
        town = validated_data.pop("town")
        state = validated_data.pop("state")
        zip_code = validated_data.pop("zip_code")
        validated_data.pop("password2")  # remove password2

        # Split full name
        full_name = validated_data.pop("full_name").strip()
        name_parts = full_name.split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:])  # support middle names

        # Create user
        user = User(
            first_name=first_name,
            last_name=last_name,
            **validated_data
        )
        user.set_password(validated_data["password"])
        user.save()

        # Create address entry
        Address.objects.create(
            user=user,
            home_address=home_address,
            town=town,
            state=state,
            zip_code=zip_code
        )
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
    

class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ['id', 'type', 'name']

class ProofOfIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProofOfIdentity
        fields = ['id', 'document_type', 'document_number', 'document_file_front', 'document_file_back', 'status', 'submitted_at']
        read_only_fields = ['status', 'submitted_at']


class ProofOfAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProofOfAddress
        fields = ['id', 'address_type', 'document_type', 'document_file', 'status', 'submitted_at']
        read_only_fields = ['status', 'submitted_at']


class HelpCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpCenter
        fields = '__all__'
        read_only_fields = ['id', 'timestamp']


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.full_name", read_only=True)
    sender = serializers.PrimaryKeyRelatedField(read_only=True)
    ticket = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Message
        fields = ["id", "sender", "sender_name", 'ticket', "text", "created_at"]

    def to_representation(self, instance):
        # Get the default serialized data
        data = super().to_representation(instance)

        # Access the current user
        request = self.context.get("request")
        user = getattr(request, "user", None)

        # Example: mark if this message was sent by the current user
        data["is_mine"] = instance.sender == user

        return data
    
class TicketSerializer(serializers.ModelSerializer):
    creator_name = serializers.CharField(source='user.full_name')
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = ["ticket_id", "subject", "status", "created_at", "messages", 'creator_name']


class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.username", read_only=True)
    recipient_name = serializers.CharField(source="recipient.username", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "recipient_name",
            "sender",
            "sender_name",
            "title",
            "message",
            "url",
            "type",
            "is_read",
            "metadata",
            "created_at",
            "read_at",
        ]
        read_only_fields = ["id", "created_at", "read_at", "sender_name", "recipient_name"]