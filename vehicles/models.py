from decimal import Decimal
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
    variant = models.CharField(max_length=50, blank=True)
    manufacture_year = models.PositiveIntegerField(db_index=True)
    purchase_date = models.DateField(null=True, blank=True)
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
    registration_state = models.CharField(max_length=100, blank=True)
    registration_city = models.CharField(max_length=100, blank=True)
    owner_name = models.CharField(max_length=150, blank=True)
    registration_date = models.DateField(null=True, blank=True)
    fitness_upto = models.DateField(null=True, blank=True)
    insurance_upto = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Vehicle'
        verbose_name_plural = 'Vehicles'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.make} {self.model} ({self.registration_number})"


class VehicleModelSpec(AuditableModel):
    """
    Master vehicle technical specification catalog.
    """
    make = models.CharField(max_length=50, db_index=True)
    model = models.CharField(max_length=50, db_index=True)
    variant = models.CharField(max_length=50, blank=True)
    segment = models.CharField(max_length=50, blank=True)
    fuel_type = models.CharField(max_length=20, blank=True)
    engine_type = models.CharField(max_length=50, blank=True)
    displacement = models.PositiveIntegerField(null=True, blank=True)
    cylinder = models.PositiveSmallIntegerField(null=True, blank=True)
    transmission_type = models.CharField(max_length=30, blank=True)
    gear_box = models.CharField(max_length=30, blank=True)
    max_power = models.CharField(max_length=50, blank=True)
    max_torque = models.CharField(max_length=50, blank=True)
    gross_weight = models.PositiveIntegerField(null=True, blank=True)
    length = models.PositiveIntegerField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    airbags = models.PositiveSmallIntegerField(default=2)
    is_esc = models.BooleanField(default=False)
    is_tpms = models.BooleanField(default=False)
    is_parking_sensors = models.BooleanField(default=False)
    is_parking_camera = models.BooleanField(default=False)
    ncap_rating = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal('0.0'))
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Vehicle Model Specification'
        verbose_name_plural = 'Vehicle Model Specifications'
        ordering = ['make', 'model', 'variant']

    def __str__(self):
        return f"{self.make} {self.model} {self.variant} ({self.segment})"


class AreaRisk(AuditableModel):
    """
    Actuarial regional risk assessment metrics.
    """
    state = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    vehicle_theft_rate_area = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.0000'),
    )
    accident_hotspot_flag = models.BooleanField(default=False)
    avg_repair_cost_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
    )

    class Meta:
        verbose_name = 'Area Risk'
        verbose_name_plural = 'Area Risks'
        ordering = ['state', 'city']

    def __str__(self):
        return f"{self.city}, {self.state} (Theft Rate: {self.vehicle_theft_rate_area})"
