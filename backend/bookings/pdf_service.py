import io
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


# Color Palette matching RentBee theme
PRIMARY_COLOR = colors.HexColor('#D97745')       # Warm RentBee Orange
PRIMARY_DARK = colors.HexColor('#9D4C29')        # Deep Rust Orange
TEXT_DARK = colors.HexColor('#352720')           # Dark Chocolate
TEXT_MUTED = colors.HexColor('#6B7280')          # Gray 500
BG_LIGHT = colors.HexColor('#FFF9F5')            # Soft Cream / Amber Light
BG_HEADER = colors.HexColor('#352720')           # Header Table Dark
SUCCESS_COLOR = colors.HexColor('#059669')       # Emerald 600
SUCCESS_BG = colors.HexColor('#ECFDF5')          # Emerald 50
BORDER_COLOR = colors.HexColor('#FDBA74')        # Orange 300 / Border
BORDER_LIGHT = colors.HexColor('#E5E7EB')        # Gray 200


def get_pdf_styles():
    base_styles = getSampleStyleSheet()

    styles = {
        'Logo': ParagraphStyle(
            'RentBeeLogo',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=28,
            textColor=PRIMARY_COLOR,
        ),
        'Tagline': ParagraphStyle(
            'RentBeeTagline',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=TEXT_MUTED,
        ),
        'DocTitle': ParagraphStyle(
            'DocTitle',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=TEXT_DARK,
            alignment=2,  # Right-aligned
        ),
        'DocSubtitle': ParagraphStyle(
            'DocSubtitle',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=13,
            textColor=SUCCESS_COLOR,
            alignment=2,
        ),
        'SectionHeader': ParagraphStyle(
            'SectionHeader',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=PRIMARY_DARK,
        ),
        'Label': ParagraphStyle(
            'Label',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            textColor=TEXT_DARK,
        ),
        'Value': ParagraphStyle(
            'Value',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=TEXT_DARK,
        ),
        'ValueMuted': ParagraphStyle(
            'ValueMuted',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=TEXT_MUTED,
        ),
        'TableHeader': ParagraphStyle(
            'TableHeader',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=colors.white,
        ),
        'TableCell': ParagraphStyle(
            'TableCell',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=TEXT_DARK,
        ),
        'TableCellBold': ParagraphStyle(
            'TableCellBold',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            textColor=TEXT_DARK,
        ),
        'TableCellRight': ParagraphStyle(
            'TableCellRight',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=TEXT_DARK,
            alignment=2,
        ),
        'TableCellRightBold': ParagraphStyle(
            'TableCellRightBold',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=TEXT_DARK,
            alignment=2,
        ),
        'TotalLabel': ParagraphStyle(
            'TotalLabel',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=TEXT_DARK,
            alignment=2,
        ),
        'TotalValue': ParagraphStyle(
            'TotalValue',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=15,
            textColor=PRIMARY_DARK,
            alignment=2,
        ),
        'BadgePaid': ParagraphStyle(
            'BadgePaid',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=11,
            textColor=SUCCESS_COLOR,
            alignment=1,
        ),
        'FooterNote': ParagraphStyle(
            'FooterNote',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=7.5,
            leading=10,
            textColor=TEXT_MUTED,
            alignment=1,
        ),
    }

    return styles


def format_address(addr_data):
    """Formats address dictionary or address model instance into human-readable multi-line string."""
    if not addr_data:
        return 'Not provided'
    if isinstance(addr_data, dict):
        if addr_data.get('full_formatted_address'):
            return addr_data['full_formatted_address']
        parts = [
            addr_data.get('house_number'),
            addr_data.get('address'),
            addr_data.get('area'),
            addr_data.get('landmark'),
            addr_data.get('city'),
            addr_data.get('state'),
            addr_data.get('pincode'),
        ]
        return ', '.join([p for p in parts if p]) or 'Not provided'
    # Address model instance
    parts = [
        getattr(addr_data, 'house_number', ''),
        getattr(addr_data, 'address', ''),
        getattr(addr_data, 'area', ''),
        getattr(addr_data, 'landmark', ''),
        getattr(addr_data, 'city', ''),
        getattr(addr_data, 'state', ''),
        getattr(addr_data, 'pincode', ''),
    ]
    return ', '.join([p for p in parts if p]) or 'Not provided'


def generate_booking_invoice_pdf(booking):
    """
    Generates a byte-level PDF Tax Invoice & Payment Receipt for a verified booking.
    Strictly requires payment_status == 'paid'.
    Reuses immutable database pricing and audit timestamps.
    """
    if booking.payment_status != 'paid':
        raise ValueError("Invoice and payment receipt can only be generated for verified paid bookings.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = get_pdf_styles()
    story = []

    # 1. Header: RentBee Branding & Document Title
    header_data = [
        [
            Paragraph("<b>RentBee</b>", styles['Logo']),
            Paragraph("<b>INVOICE & PAYMENT RECEIPT</b>", styles['DocTitle']),
        ],
        [
            Paragraph("Peer-to-Peer Equipment Rental Platform<br/>support@rentbee.com | www.rentbee.com", styles['Tagline']),
            Paragraph(f"<b>STATUS: PAYMENT VERIFIED</b>", styles['DocSubtitle']),
        ]
    ]
    header_table = Table(header_data, colWidths=[3.25 * inch, 4.25 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    # Divider Line
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceBefore=4, spaceAfter=12))

    # 2. Key Metadata Summary (Invoice No, Booking Ref, Dates, Payment Method)
    invoice_number = f"INV-{booking.booking_reference}"
    booking_date_str = timezone.localtime(booking.created_at).strftime('%d %b %Y, %I:%M %p')
    generation_date_str = timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p')
    payment_date_str = (
        timezone.localtime(booking.payment_verified_at).strftime('%d %b %Y, %I:%M %p')
        if booking.payment_verified_at else 'Verified'
    )

    is_online = booking.payment_method == 'online'
    payment_method_display = "Online Payment (Razorpay)" if is_online else "Offline Pay at Pickup (Cash)"
    transaction_id_display = (
        booking.payment_transaction_id or 'Verified via Razorpay Gateway'
        if is_online else 'N/A (Cash Handover Confirmed at Pickup)'
    )

    meta_left = [
        [Paragraph("Invoice / Receipt No:", styles['Label']), Paragraph(f"<b>{invoice_number}</b>", styles['Value'])],
        [Paragraph("Booking ID / Ref:", styles['Label']), Paragraph(f"<b>{booking.booking_reference}</b> (#{booking.id})", styles['Value'])],
        [Paragraph("Booking Date:", styles['Label']), Paragraph(booking_date_str, styles['Value'])],
        [Paragraph("Receipt Generated:", styles['Label']), Paragraph(generation_date_str, styles['Value'])],
    ]
    meta_right = [
        [Paragraph("Payment Status:", styles['Label']), Paragraph("<b>PAID (Verified)</b>", styles['TableCellBold'])],
        [Paragraph("Payment Method:", styles['Label']), Paragraph(payment_method_display, styles['Value'])],
        [Paragraph("Transaction ID:", styles['Label']), Paragraph(f"<font size=7.5>{transaction_id_display}</font>", styles['Value'])],
        [Paragraph("Payment Date:", styles['Label']), Paragraph(payment_date_str, styles['Value'])],
    ]

    meta_table_left = Table(meta_left, colWidths=[1.5 * inch, 2.15 * inch])
    meta_table_left.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    meta_table_right = Table(meta_right, colWidths=[1.4 * inch, 2.45 * inch])
    meta_table_right.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    meta_container = Table([[meta_table_left, meta_table_right]], colWidths=[3.75 * inch, 3.75 * inch])
    meta_container.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_container)
    story.append(Spacer(1, 14))

    # 3. Customer (Renter) & Owner (Host) Details
    renter_name = booking.renter.full_name or booking.renter.username or 'Customer'
    renter_email = booking.renter.email or 'N/A'
    renter_phone = booking.renter.phone_number or 'N/A'
    renter_addr = format_address(booking.renter_address_data or (booking.renter.addresses.first() if hasattr(booking.renter, 'addresses') else None))

    owner_name = booking.owner.full_name or booking.owner.username or 'Host'
    owner_email = booking.owner.email or 'N/A'
    owner_phone = booking.owner.phone_number or 'N/A'
    owner_addr = format_address(booking.owner.addresses.first() if hasattr(booking.owner, 'addresses') else None)

    party_data = [
        [
            Paragraph("<b>CUSTOMER (RENTER) DETAILS</b>", styles['SectionHeader']),
            Paragraph("<b>EQUIPMENT OWNER (HOST) DETAILS</b>", styles['SectionHeader']),
        ],
        [
            Paragraph(
                f"<b>{renter_name}</b><br/>"
                f"Email: {renter_email}<br/>"
                f"Phone: {renter_phone}<br/>"
                f"Address: {renter_addr}",
                styles['Value']
            ),
            Paragraph(
                f"<b>{owner_name}</b><br/>"
                f"Email: {owner_email}<br/>"
                f"Phone: {owner_phone}<br/>"
                f"Pickup Location: {owner_addr}",
                styles['Value']
            ),
        ]
    ]
    party_table = Table(party_data, colWidths=[3.75 * inch, 3.75 * inch])
    party_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (0, 0), 0.75, PRIMARY_COLOR),
        ('LINEBELOW', (1, 0), (1, 0), 0.75, PRIMARY_COLOR),
    ]))
    story.append(party_table)
    story.append(Spacer(1, 14))

    # 4. Rental Reservation & Schedule Details
    category_name = booking.item.category.name if getattr(booking.item, 'category', None) else 'Equipment'
    start_str = booking.start_date.strftime('%d %b %Y')
    end_str = booking.end_date.strftime('%d %b %Y')
    duration_str = f"{booking.duration_days} day{'s' if booking.duration_days != 1 else ''}"
    quantity_str = f"{booking.requested_quantity} unit{'s' if booking.requested_quantity != 1 else ''}"

    res_data = [
        [
            Paragraph("<b>RENTAL RESERVATION DETAILS</b>", styles['SectionHeader']),
            Paragraph("", styles['Value'])
        ],
        [
            Paragraph("<b>Item Name:</b>", styles['Label']),
            Paragraph(f"<b>{booking.item.name}</b> (Category: {category_name})", styles['Value'])
        ],
        [
            Paragraph("<b>Rental Schedule:</b>", styles['Label']),
            Paragraph(f"{start_str} to {end_str} ({duration_str})", styles['Value'])
        ],
        [
            Paragraph("<b>Requested Quantity:</b>", styles['Label']),
            Paragraph(quantity_str, styles['Value'])
        ],
    ]
    res_table = Table(res_data, colWidths=[1.75 * inch, 5.75 * inch])
    res_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (0, 0), (1, 0)),
        ('LINEBELOW', (0, 0), (1, 0), 0.75, PRIMARY_COLOR),
    ]))
    story.append(res_table)
    story.append(Spacer(1, 14))

    # 5. Itemized Price Breakdown Table
    # Part 2: Display rental charge and security deposit separately.
    item_header = [
        Paragraph("Description", styles['TableHeader']),
        Paragraph("Rate / Duration / Qty", styles['TableHeader']),
        Paragraph("Amount (INR)", styles['TableHeader']),
    ]

    rate_calc = f"₹{booking.daily_price:,.2f}/day × {booking.duration_days}d × {booking.requested_quantity}u"

    has_discount = bool(getattr(booking, 'discount_amount', 0) and booking.discount_amount > 0)
    items_data = [item_header]

    if has_discount:
        original_rental = getattr(booking, 'original_rental_amount', None) or (booking.rental_amount + booking.discount_amount)
        rental_row = [
            Paragraph(f"<b>Rental Charge (Original):</b> {booking.item.name}", styles['TableCell']),
            Paragraph(rate_calc, styles['TableCell']),
            Paragraph(f"₹{original_rental:,.2f}", styles['TableCellRight']),
        ]
        discount_row = [
            Paragraph("<b>First Booking Discount (10% OFF):</b> Promotional Welcome Offer", styles['TableCell']),
            Paragraph("10% deduction applied to rental fee", styles['ValueMuted']),
            Paragraph(f"-₹{booking.discount_amount:,.2f}", styles['TableCellRightBold']),
        ]
        items_data.append(rental_row)
        items_data.append(discount_row)
    else:
        rental_row = [
            Paragraph(f"<b>Rental Charge:</b> {booking.item.name}", styles['TableCell']),
            Paragraph(rate_calc, styles['TableCell']),
            Paragraph(f"₹{booking.rental_amount:,.2f}", styles['TableCellRight']),
        ]
        items_data.append(rental_row)

    deposit_row = [
        Paragraph("<b>Security Deposit:</b> Refundable upon safe return", styles['TableCell']),
        Paragraph("Held securely during rental period", styles['ValueMuted']),
        Paragraph(f"₹{booking.deposit_amount:,.2f}", styles['TableCellRight']),
    ]
    items_data.append(deposit_row)

    total_idx = len(items_data)
    total_row = [
        Paragraph("<b>TOTAL AMOUNT PAID</b>", styles['TotalLabel']),
        Paragraph("", styles['TableCell']),
        Paragraph(f"<b>₹{booking.total_amount:,.2f}</b>", styles['TotalValue']),
    ]
    items_data.append(total_row)

    table_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), BG_HEADER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, total_idx - 1), 0.5, BORDER_LIGHT),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('SPAN', (0, total_idx), (1, total_idx)),
        ('BACKGROUND', (0, total_idx), (-1, total_idx), colors.HexColor('#FEF3C7')),  # Warm Amber highlight
        ('LINEABOVE', (0, total_idx), (-1, total_idx), 1, PRIMARY_COLOR),
        ('BOX', (0, 0), (-1, -1), 1, PRIMARY_COLOR),
    ]

    if has_discount:
        table_styles.append(('BACKGROUND', (0, 2), (-1, 2), SUCCESS_BG))
        table_styles.append(('BACKGROUND', (0, 3), (-1, 3), BG_LIGHT))
    else:
        table_styles.append(('BACKGROUND', (0, 2), (-1, 2), BG_LIGHT))

    items_table = Table(items_data, colWidths=[3.75 * inch, 2.25 * inch, 1.5 * inch])
    items_table.setStyle(TableStyle(table_styles))
    story.append(items_table)
    story.append(Spacer(1, 16))

    # 6. Payment Receipt Verification Box (Part 3 & 4)
    verified_by_text = "Automated Gateway Verification (Razorpay)"
    if not is_online:
        host_verifier = booking.payment_verified_by.full_name if booking.payment_verified_by else owner_name
        verified_by_text = f"Confirmed in Person by Host: {host_verifier}"

    receipt_box_data = [
        [
            Paragraph("<b>OFFICIAL PAYMENT CONFIRMATION</b>", styles['SectionHeader']),
            Paragraph(f"<b>Verified Amount: ₹{booking.total_amount:,.2f}</b>", styles['DocSubtitle']),
        ],
        [
            Paragraph(
                f"<b>Payment Status:</b> Payment Verified (Paid in Full)<br/>"
                f"<b>Payment Method:</b> {payment_method_display}<br/>"
                f"<b>Transaction / Reference:</b> {transaction_id_display}<br/>"
                + (f"<b>Razorpay Order ID:</b> {booking.razorpay_order_id}<br/>" if is_online and booking.razorpay_order_id else "")
                + f"<b>Verified Timestamp:</b> {payment_date_str}<br/>"
                f"<b>Verification Authority:</b> {verified_by_text}",
                styles['Value']
            ),
            Paragraph(
                "<font color='#059669'><b>✔ VERIFIED & RECORDED</b></font><br/>"
                "This document serves as your official tax invoice and proof of rental payment on RentBee.<br/><br/>"
                "<i>Please retain this receipt for your records and present it upon item pickup if requested.</i>",
                styles['ValueMuted']
            )
        ]
    ]
    receipt_box = Table(receipt_box_data, colWidths=[4.25 * inch, 3.25 * inch])
    receipt_box.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), SUCCESS_BG),
        ('BOX', (0, 0), (-1, -1), 1, SUCCESS_COLOR),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, SUCCESS_COLOR),
    ]))
    story.append(receipt_box)
    story.append(Spacer(1, 16))

    # 7. Terms & Footer Notes
    terms_text = (
        "<b>Terms & Security Deposit Notes:</b><br/>"
        "• Security deposits are held safely in trust and refunded in full upon verified item return in acceptable condition.<br/>"
        "• Cancellations and problem reports must be submitted through the RentBee platform prior to physical item handover.<br/>"
        "• This is an electronically generated receipt issued by RentBee Technologies. No physical signature is required."
    )
    story.append(Paragraph(terms_text, styles['ValueMuted']))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_LIGHT, spaceBefore=4, spaceAfter=8))
    story.append(Paragraph(
        "RentBee • Peer-to-Peer Equipment Rentals • Connecting Verified Communities • © 2026 RentBee Inc.",
        styles['FooterNote']
    ))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

