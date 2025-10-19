import cloudinary
import cloudinary.uploader
import os 
from dotenv import load_dotenv

load_dotenv()

def upload_media(file_path, folder="exam_media"):
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET')
)
    upload_result = cloudinary.uploader.upload(file_path, folder=folder, resource_type="auto")
    return {
        "url": upload_result.get("secure_url"),
        "public_id": upload_result.get("public_id"),
        "format": upload_result.get("format"),
        "size": upload_result.get("bytes"),
    }