from io import BytesIO
from decimal import Decimal
from typing import Optional
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from policies.models import Policy


class PolicyCertificateService:
    """
    Generates professional, regulatory-aligned Certificate of Motor Insurance
    and Policy Schedule documents in PDF format for vehicle insurance policies.
    """

    @classmethod
    def generate_certificate_pdf(cls, policy: Policy) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        
        # Custom styles
        header_title_style = ParagraphStyle(
            'CertHeaderTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#0f172a'),
        )
        header_sub_style = ParagraphStyle(
            'CertHeaderSub',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#0284c7'),
        )
        notice_style = ParagraphStyle(
            'CertNotice',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#64748b'),
            alignment=1,  # Center
        )
        section_heading = ParagraphStyle(
            'CertSectionHeading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=12,
            textColor=colors.HexColor('#0f172a'),
        )
        cell_bold = ParagraphStyle(
            'CertCellBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#1e293b'),
        )
        cell_regular = ParagraphStyle(
            'CertCellRegular',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#334155'),
        )
        cell_mono = ParagraphStyle(
            'CertCellMono',
            parent=styles['Normal'],
            fontName='Courier-Bold',
            fontSize=9,
            leading=11,
            textColor=colors.HexColor('#0f172a'),
        )
        footer_style = ParagraphStyle(
            'CertFooter',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor('#94a3b8'),
            alignment=1,
        )

        story = []

        # 1. Header Banner
        customer_user = policy.customer.user
        cust_name = customer_user.get_full_name() or customer_user.username
        status_color = '#10b981' if policy.status == 'ACTIVE' else ('#0284c7' if policy.status == 'RENEWED' else '#ef4444')

        header_data = [
            [
                Paragraph("<b>NEXISURE DIGITAL ASSURANCE</b><br/><font size='9' color='#64748b'>Underwriting & Risk Protection Services</font>", styles['Normal']),
                Paragraph(f"<font color='{status_color}'><b>● {policy.get_status_display().upper()}</b></font><br/><font size='8' color='#64748b'>Ref: CERT-{policy.policy_number}</font>", ParagraphStyle('RAlign', parent=styles['Normal'], alignment=2)),
            ]
        ]
        header_table = Table(header_data, colWidths=[340, 200])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 8))

        # Title
        story.append(Paragraph("CERTIFICATE OF MOTOR INSURANCE & POLICY SCHEDULE", header_title_style))
        story.append(Paragraph("Issued in compliance with Nexisure Vehicle Insurance Standards", header_sub_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph("<b>NOTICE:</b> Simulated Insurance Platform — Academic Demonstration and Functional Prototype Only. Financial values shown in Indian Rupees (INR / ₹).", notice_style))
        story.append(Spacer(1, 10))

        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=10))

        # 2. Key Contract Schedule Table
        contract_data = [
            [
                Paragraph("<b>Policy Number:</b>", cell_bold),
                Paragraph(f"{policy.policy_number}", cell_mono),
                Paragraph("<b>Period of Insurance:</b>", cell_bold),
                Paragraph(f"{policy.start_date.strftime('%d %b %Y')} to {policy.end_date.strftime('%d %b %Y')}", cell_regular),
            ],
            [
                Paragraph("<b>Contract Status:</b>", cell_bold),
                Paragraph(f"{policy.get_status_display()}", cell_regular),
                Paragraph("<b>Term Duration:</b>", cell_bold),
                Paragraph(f"{policy.duration_years} Year(s)", cell_regular),
            ],
            [
                Paragraph("<b>Issuance Date:</b>", cell_bold),
                Paragraph(f"{policy.created_at.strftime('%d %b %Y')}", cell_regular),
                Paragraph("<b>Underwriting Channel:</b>", cell_bold),
                Paragraph(f"{policy.underwriter.user.get_full_name() if policy.underwriter else 'Nexisure Automated Engine'}", cell_regular),
            ],
        ]

        if policy.previous_policy:
            contract_data.append([
                Paragraph("<b>Renewal Lineage:</b>", cell_bold),
                Paragraph(f"Renewed from <b>{policy.previous_policy.policy_number}</b>", cell_regular),
                Paragraph("<b>NCB Applied:</b>", cell_bold),
                Paragraph("5% No-Claim Bonus Applied", cell_regular),
            ])

        contract_table = Table(contract_data, colWidths=[110, 160, 110, 160])
        contract_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(contract_table)
        story.append(Spacer(1, 12))

        # 3. Policyholder & Insured Vehicle (Side by Side)
        story.append(Paragraph("POLICYHOLDER & INSURED VEHICLE ASSET", section_heading))
        story.append(Spacer(1, 4))

        cust_addr_parts = [part for part in [policy.customer.address_line, policy.customer.city, policy.customer.postal_code] if part]
        cust_addr_str = ", ".join(cust_addr_parts) if cust_addr_parts else "Not Provided"

        customer_vehicle_data = [
            [
                Paragraph("<b>POLICYHOLDER DETAILS</b>", cell_bold),
                Paragraph("<b>INSURED VEHICLE SPECIFICATIONS</b>", cell_bold),
            ],
            [
                Paragraph(f"<b>Name:</b> {cust_name}<br/>"
                          f"<b>Customer Code:</b> {policy.customer.customer_code}<br/>"
                          f"<b>Email:</b> {customer_user.email}<br/>"
                          f"<b>Phone:</b> {customer_user.phone_number or 'N/A'}<br/>"
                          f"<b>Address:</b> {cust_addr_str}", cell_regular),
                Paragraph(f"<b>Registration Plate:</b> <b>{policy.vehicle.registration_number}</b><br/>"
                          f"<b>Make & Model:</b> {policy.vehicle.make} {policy.vehicle.model} ({policy.vehicle.manufacture_year})<br/>"
                          f"<b>Chassis / VIN:</b> {policy.vehicle.chassis_number}<br/>"
                          f"<b>Vehicle Type:</b> {policy.vehicle.get_vehicle_type_display()} ({policy.vehicle.get_fuel_type_display()})<br/>"
                          f"<b>Insured Declared Value (IDV):</b> <b>₹{policy.vehicle.vehicle_value:,.2f}</b>", cell_regular),
            ],
        ]
        cv_table = Table(customer_vehicle_data, colWidths=[270, 270])
        cv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(cv_table)
        story.append(Spacer(1, 12))

        # 4. Coverage Plan Inclusions & Features
        story.append(Paragraph("COVERAGE PLAN & RIDER INCLUSIONS", section_heading))
        story.append(Spacer(1, 4))

        plan = policy.coverage_plan
        cov_rows = [
            [
                Paragraph("<b>Coverage Tier:</b>", cell_bold),
                Paragraph(f"<b>{plan.name}</b> ({plan.plan_code})", cell_regular),
                Paragraph("<b>Third-Party Liability:</b>", cell_bold),
                Paragraph("<font color='#10b981'><b>✓ INCLUDED</b></font> (Mandatory Statutory Limit)", cell_regular),
            ],
            [
                Paragraph("<b>Description:</b>", cell_bold),
                Paragraph(f"{plan.description}", cell_regular),
                Paragraph("<b>Own Damage Protection:</b>", cell_bold),
                Paragraph("<font color='#10b981'><b>✓ INCLUDED</b></font>" if plan.includes_own_damage else "<font color='#ef4444'>✗ NOT INCLUDED</font>", cell_regular),
            ],
            [
                Paragraph("<b>Base Rate Applied:</b>", cell_bold),
                Paragraph(f"{plan.base_rate_percentage}% of vehicle IDV", cell_regular),
                Paragraph("<b>Roadside Assistance:</b>", cell_bold),
                Paragraph("<font color='#10b981'><b>✓ INCLUDED</b></font>" if plan.includes_roadside_assistance else "<font color='#ef4444'>✗ NOT INCLUDED</font>", cell_regular),
            ],
            [
                Paragraph("<b>Deductible Type:</b>", cell_bold),
                Paragraph("Standard Compulsory Excess", cell_regular),
                Paragraph("<b>Engine Protection:</b>", cell_bold),
                Paragraph("<font color='#10b981'><b>✓ INCLUDED</b></font>" if plan.includes_engine_protection else "<font color='#ef4444'>✗ NOT INCLUDED</font>", cell_regular),
            ],
        ]
        cov_table = Table(cov_rows, colWidths=[110, 160, 110, 160])
        cov_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(cov_table)
        story.append(Spacer(1, 12))

        # 5. Financial Terms & Locked Schedule
        story.append(Paragraph("FINANCIAL SCHEDULE & PREMIUM BREAKDOWN", section_heading))
        story.append(Spacer(1, 4))

        fin_data = [
            [
                Paragraph("<b>Insured Declared Value (IDV)</b>", cell_bold),
                Paragraph("<b>Compulsory Deductible</b>", cell_bold),
                Paragraph("<b>Term Duration</b>", cell_bold),
                Paragraph("<b>Locked Premium (₹)</b>", cell_bold),
            ],
            [
                Paragraph(f"₹{policy.vehicle.vehicle_value:,.2f}", cell_mono),
                Paragraph(f"₹{policy.deductible_amount:,.2f}", cell_mono),
                Paragraph(f"{policy.duration_years} Year(s)", cell_regular),
                Paragraph(f"<font color='#0284c7'><b>₹{policy.premium_amount:,.2f}</b></font>", cell_mono),
            ],
        ]
        fin_table = Table(fin_data, colWidths=[135, 135, 135, 135])
        fin_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(fin_table)
        story.append(Spacer(1, 14))

        # 6. Legal Terms & Signatory Block
        sig_data = [
            [
                Paragraph("<b>IMPORTANT NOTICE & CONDITIONS:</b><br/>"
                          "1. This certificate evidence coverage under the terms and exceptions of the Nexisure policy.<br/>"
                          "2. Persons or classes of persons entitled to drive: Any person holding an active, valid driving license.<br/>"
                          "3. Limitations as to use: Use in connection with the policyholder's vehicle registration as documented.<br/>"
                          "4. Financial terms are immutably locked for the policy duration upon issuance.<br/>"
                          "5. In the event of an incident, notify Nexisure Claims Operations within 48 hours.", cell_regular),
                Paragraph("<b>DIGITALLY AUTHORIZED BY:</b><br/><br/>"
                          "<b>Nexisure Underwriting Committee</b><br/>"
                          f"Officer: {policy.underwriter.user.get_full_name() if policy.underwriter else 'System Underwriting Authority'}<br/>"
                          f"Timestamp: {policy.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}<br/>"
                          "<i>Digitally Signed & Validated</i>", cell_regular),
            ]
        ]
        sig_table = Table(sig_data, colWidths=[340, 200])
        sig_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 12))

        story.append(Paragraph(
            "Nexisure Simulated Vehicle Insurance Platform • Academic Demonstration • Not for Commercial Production Use",
            footer_style
        ))

        doc.build(story)
        return buffer.getvalue()
