import os
import time
import requests
import dropbox
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Replace this with your album name
GOOGLE_PHOTOS_ALBUM_NAME = "Leah and Ryan's Wedding"
GOOGLE_PHOTOS_SCOPES = ['https://www.googleapis.com/auth/photoslibrary']

# Google Photos Setup
def get_google_photos_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", GOOGLE_PHOTOS_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", GOOGLE_PHOTOS_SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("photoslibrary", "v1", credentials=creds, static_discovery=False)

photos_service = get_google_photos_service()

# Get Album ID or Create if Not Found
def get_album_id(service, album_name):
    response = service.albums().list(pageSize=50).execute()
    for album in response.get("albums", []):
        if album["title"] == album_name:
            return album["id"]
    album = service.albums().create(body={"album": {"title": album_name}}).execute()
    return album["id"]

album_id = get_album_id(photos_service, GOOGLE_PHOTOS_ALBUM_NAME)
print(f"The name of the album is: {GOOGLE_PHOTOS_ALBUM_NAME}")

# Upload a file to Google Photos
def upload_to_google_photos(service, album_id, file_path):
    file_name = os.path.basename(file_path)
    headers = {
        "Authorization": f"Bearer {service._http.credentials.token}",
        "Content-Type": "application/octet-stream",
        "X-Goog-Upload-Content-Type": "image/png",
        "X-Goog-Upload-Protocol": "raw",
    }
    with open(file_path, 'rb') as file:
        response = requests.post(
            "https://photoslibrary.googleapis.com/v1/uploads",
            headers=headers,
            data=file
        )
    upload_token = response.text
    PhotoDescription = "Uploaded by "+" ".join(file_name.rsplit('.', 1)[0].split()[1:])
    new_media_item = {
        "newMediaItems": [
            {
                "description": PhotoDescription,
                "simpleMediaItem": {
                    "uploadToken": upload_token
                }
            }
        ],
        "albumId": album_id
    }
    response = service.mediaItems().batchCreate(body=new_media_item).execute()
    print(f"File '{file_name}' uploaded successfully to Google Photos")

# Dropbox OAuth2 Setup
# Replace with your app credentials and generated refresh token
CLIENT_ID = "uj0o6l8y9nsk2em"  # Replace with your Dropbox app's client ID
CLIENT_SECRET = "288xsz31nhf4qrg"  # Replace with your Dropbox app's client secret
REFRESH_TOKEN = "nD5ddviXocMAAAAAAAAAAZOLAp8PRQASsxm9KnAhtBDLGsGTHWEl1vOAALQmI2vx"  # Replace with the generated refresh token
ACCESS_TOKEN = None  # Will be dynamically updated

def refresh_access_token(refresh_token, client_id, client_secret):
    url = "https://api.dropboxapi.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post(url, data=data)
    response.raise_for_status()  # Raises an error if the HTTP request failed
    return response.json()

def get_dropbox_client():
    global ACCESS_TOKEN, ACCESS_TOKEN_EXPIRY
    if ACCESS_TOKEN is None or (ACCESS_TOKEN_EXPIRY and time.time() >= ACCESS_TOKEN_EXPIRY):
        tokens = refresh_access_token(REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET)
        ACCESS_TOKEN = tokens['access_token']
        # Assuming tokens include expiry info in seconds; default to 4 hours (14400 seconds) if not provided
        ACCESS_TOKEN_EXPIRY = time.time() + tokens.get('expires_in', 14400)
    return dropbox.Dropbox(ACCESS_TOKEN)

dbx = get_dropbox_client()

# Function to list contents in the Dropbox folder
def list_dropbox_folder(folder_path):
    try:
        result = dbx.files_list_folder(folder_path)
        return [entry.name for entry in result.entries if isinstance(entry, dropbox.files.FileMetadata)]
    except dropbox.exceptions.ApiError as e:
        print(f"Error listing folders: {e}")
        return []

# Function to download a file from Dropbox
def download_file_from_dropbox(file_name, folder_path, local_path):
    try:
        dropbox_path = f"{folder_path}/{file_name}"
        with open(local_path, "wb") as f:
            metadata, res = dbx.files_download(path=dropbox_path)
            f.write(res.content)
        print(f"File '{file_name}' downloaded successfully to '{local_path}'")
    except dropbox.exceptions.ApiError as e:
        print(f"Error downloading file: {e}")

# Function to delete a file from Dropbox
def delete_file_from_dropbox(file_name, folder_path):
    try:
        dropbox_path = f"{folder_path}/{file_name}"
        dbx.files_delete_v2(dropbox_path)
        print(f"File '{file_name}' deleted successfully from Dropbox")
    except dropbox.exceptions.ApiError as e:
        print(f"Error deleting file: {e}")

# Main function to download files from Dropbox and upload them to Google Photos
def process_files_from_dropbox_to_google_photos():
    global dbx  # Reassign the Dropbox client if the token was refreshed
    folder_path = "/File requests/Wedding Uploads"  # Replace with your Dropbox folder path
    local_download_path = r'C:\Users\RyanBaker\Downloads\Wedding Uploads'  # Adjust to your desired local folder

    current_files = list_dropbox_folder(folder_path)
    for file_name in current_files:
        local_file_path = os.path.join(local_download_path, file_name)
        download_file_from_dropbox(file_name, folder_path, local_file_path)
        upload_to_google_photos(photos_service, album_id, local_file_path)
        delete_file_from_dropbox(file_name, folder_path)

# Run the process every minute
while True:
    # Refresh Dropbox client every iteration to ensure valid token
    dbx = get_dropbox_client()
    process_files_from_dropbox_to_google_photos()
    time.sleep(60)
