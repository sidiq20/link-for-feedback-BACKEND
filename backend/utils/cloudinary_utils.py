import cloudinary 
import cloudinary.uploader
from dotenv import load_dotenv
import os 

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def uploader_media(file):
    result = cloudinary.uploader.upload(file, folder="exam_media") 
    return result.get("secure_url")