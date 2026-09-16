from django.db import models
from core.models import AuditableModel
from customers.models import CustomerProfile


class VehicleType(models.TextChoices):
    SEDAN = 'SEDAN', 'Sedan'
    SUV = 'SUV', 'SUV'
    HATCHBACK = 'HATCHBACK', 'Hatchback'
    TRUCK = 'TRUCK', 'Truck'
    MOTORCYCLE = 'MOTORCYCLE', 'Motorcycle'
    COMMERCIAL_VAN = 'COMMERCIAL_VAN', 'Commercial Van'


class FuelType(models.TextChoices):
    PETROL = 'PETROL', 'Petrol'
    DIESEL = 'DIESEL', 'Diesel'
    ELECTRIC = 'ELECTRIC', 'Electric (EV)'
    HYBRID = 'HYBRID', 'Hybrid'
    CNG = 'CNG', 'CNG'


class UsageType(models.TextChoices):
    PERSONAL = 'PERSONAL', 'Personal Commute'
    COMMERCIAL = 'COMMERCIAL', 'Commercial Business'
    RIDESHARE = 'RIDESHARE', 'Rideshare / Taxi'


class Vehicle(AuditableModel):
    """
    Vehicle asset entity.
    Maintains normalized identifiers, technical specifications,
    and valuation metrics.
    """
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name='vehicles',
    )
    registration_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text='Normalized uppercase license plate (e.g. DL01AB1234)',
    )
    vehicle_type = models.CharField(
        max_length=30,
        choices=VehicleType.choices,
        default=VehicleType.SEDAN,
    )
    make = models.CharField(max_length=50, db_index=True)
    model = models.CharField(max_length=50)
    manufacture_year = models.PositiveIntegerField(db_index=True)
    fuel_type = models.CharField(
        max_length=20,
        choices=FuelType.choices,
        default=FuelType.PETROL,
    )
    engine_number = models.CharField(max_length=50, blank=True)
    chassis_number = models.CharField(max_length=50, unique=True, db_index=True)
    vehicle_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Insured Declared Value (IDV)',
    )
    usage_type = models.CharField(
        max_length=20,
        choices=UsageType.choices,
        default=UsageType.PERSONAL,
    )

    class Meta:
        verbose_name = 'Vehicle'
        verbose_name_plural = 'Vehicles'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.make} {self.model} ({self.registration_number})"
