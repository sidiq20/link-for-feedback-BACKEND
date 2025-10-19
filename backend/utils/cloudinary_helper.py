import cloudinary
import cloudinary.uploader
import os

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_media(file, folder="whisper_exams"):
    upload_result = cloudinary.uploader.upload(
        file,
        folder=folder,
        resource_type="auto"
    )
    return upload_result["secure_url"], upload_result["public_id"], upload_result["resource_type"]
