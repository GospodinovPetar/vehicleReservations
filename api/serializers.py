from __future__ import annotations

from datetime import datetime

from django.contrib.auth import get_user_model
from rest_framework import serializers

from inventory.models.vehicle import Vehicle
from inventory.models.reservation import VehicleReservation, Location

User = get_user_model()


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "name",
            "car_type",
            "engine_type",
            "seats",
            "unlimited_seats",
            "price_per_day",
        ]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name"]


class ReservationCreateSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField()
    pickup_location_id = serializers.IntegerField()
    return_location_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date is None or end_date is None:
            raise serializers.ValidationError(
                {"date_range": ["start_date and end_date are required."]}
            )
        if end_date <= start_date:
            raise serializers.ValidationError(
                {"date_range": ["end_date must be after start_date."]}
            )
        return attrs


class ReservationSerializer(serializers.ModelSerializer):
    vehicle_name = serializers.SerializerMethodField()
    group_status = serializers.SerializerMethodField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    group_id = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = VehicleReservation
        fields = [
            "id",
            "user",
            "vehicle",
            "vehicle_name",
            "pickup_location",
            "return_location",
            "start_date",
            "end_date",
            "group_id",
            "group_status",
            "total_price",
        ]
        read_only_fields = ("user", "group_id", "group_status", "total_price")

    def get_vehicle_name(self, obj):
        snapshot = getattr(obj, "vehicle_name_snapshot", "")
        if snapshot:
            return snapshot
        vehicle_obj = getattr(obj, "vehicle", None)
        return str(vehicle_obj) if vehicle_obj is not None else ""

    def get_group_status(self, obj):
        grp = getattr(obj, "group", None)
        return getattr(grp, "status", None)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class AvailabilityVehicleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class AvailabilityPartialSliceQuoteSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()


class AvailabilityPartialSliceSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    quote = AvailabilityPartialSliceQuoteSerializer()

class PaymentRequestSerializer(serializers.Serializer):
    card_number = serializers.CharField(write_only=True)
    exp_month = serializers.IntegerField(write_only=True, min_value=1, max_value=12)
    exp_year = serializers.IntegerField(write_only=True)
    cvc = serializers.CharField(write_only=True)

    def validate(self, attrs):
        now = datetime.now()
        year = attrs["exp_year"]
        if year < now.year or year > now.year + 20:
            raise serializers.ValidationError({"exp_year": ["Invalid exp_year."]})
        return attrs

class PaymentResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    group_id = serializers.IntegerField()
    charged = serializers.CharField()

class AvailabilityPartialVehicleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slices = AvailabilityPartialSliceSerializer(many=True)


class AvailabilityResponseSerializer(serializers.Serializer):
    vehicles = AvailabilityVehicleSerializer(many=True)
    partial_vehicles = AvailabilityPartialVehicleSerializer(many=True)
