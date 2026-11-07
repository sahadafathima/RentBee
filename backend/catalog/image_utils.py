import io
import os
from PIL import Image, ImageOps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_IMAGE_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_image_file(uploaded_file):
    """Validates uploaded file size and extension."""
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"Unsupported image format '{ext}'. Allowed formats: JPG, JPEG, PNG, WEBP.")
    if uploaded_file.size > MAX_IMAGE_FILE_SIZE:
        raise ValidationError("Image file size exceeds the maximum allowed limit of 5MB.")


def process_item_image(uploaded_file, max_width=1200, max_height=900, quality=85):
    """
    Processes an uploaded image with Pillow:
    1. Validates format & file size.
    2. Corrects EXIF orientation.
    3. Resizes proportionally using LANCZOS thumbnail (max 1200x900, maintaining aspect ratio).
    4. Compresses with target quality ~85 (approx 100-250KB).
    5. Returns an InMemoryUploadedFile ready to save.
    """
    validate_image_file(uploaded_file)

    img = Image.open(uploaded_file)

    # 1. Correct orientation using EXIF transpose
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # 2. Resize proportionally (thumbnail preserves aspect ratio without stretching)
    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    # 3. Format and compress
    output_io = io.BytesIO()

    # Preserve transparency for RGBA / P PNG or WebP
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img.save(output_io, format='WEBP', quality=quality, optimize=True)
        ext = '.webp'
        content_type = 'image/webp'
    else:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(output_io, format='JPEG', quality=quality, optimize=True)
        ext = '.jpg'
        content_type = 'image/jpeg'

    output_io.seek(0)
    base_name = os.path.splitext(uploaded_file.name)[0]
    # Clean base name
    clean_base = ''.join(c for c in base_name if c.isalnum() or c in ('_', '-')) or 'item'
    new_name = f"{clean_base}{ext}"

    return InMemoryUploadedFile(
        file=output_io,
        field_name='image',
        name=new_name,
        content_type=content_type,
        size=output_io.getbuffer().nbytes,
        charset=None
    )

