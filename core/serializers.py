from decimal import Decimal
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, Event, EventMembership, Transaction, TransactionSplit


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['is_admin'] = user.is_admin
        return token


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_admin', 'password']

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class EventMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = EventMembership
        fields = ['user', 'username', 'balance']


class EventSerializer(serializers.ModelSerializer):
    memberships = EventMembershipSerializer(many=True, read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Event
        fields = ['id', 'name', 'description', 'created_by', 'created_at', 'memberships']


class TransactionSplitSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = TransactionSplit
        fields = ['user', 'username', 'amount']


class TransactionSerializer(serializers.ModelSerializer):
    splits = TransactionSplitSerializer(many=True, read_only=True)
    paid_by_username = serializers.CharField(source='paid_by.username', read_only=True)
    split_mode = serializers.ChoiceField(
        choices=['equal', 'manual'], write_only=True, default='equal'
    )
    splits_input = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False, default=list
    )

    class Meta:
        model = Transaction
        fields = [
            'id', 'description', 'amount', 'paid_by', 'paid_by_username',
            'created_at', 'splits', 'split_mode', 'splits_input'
        ]
        extra_kwargs = {'paid_by': {'write_only': True}}

    def validate(self, data):
        split_mode = data.get('split_mode', 'equal')
        splits_input = data.get('splits_input', [])

        if split_mode == 'manual':
            if not splits_input:
                raise serializers.ValidationError(
                    {'splits_input': 'splits_input is required for manual split mode.'}
                )
            total = sum(Decimal(str(s['amount'])) for s in splits_input)
            if abs(total - data['amount']) > Decimal('0.01'):
                raise serializers.ValidationError(
                    {'splits_input': f'Splits sum ({total}) must equal transaction amount ({data["amount"]}).'}
                )

        return data

    def create(self, validated_data):
        from .services import create_transaction
        split_mode = validated_data.pop('split_mode', 'equal')
        splits_input = validated_data.pop('splits_input', [])
        event = self.context['event']

        return create_transaction(
            event=event,
            description=validated_data['description'],
            amount=validated_data['amount'],
            paid_by=validated_data['paid_by'],
            split_mode=split_mode,
            splits_data=splits_input,
        )
