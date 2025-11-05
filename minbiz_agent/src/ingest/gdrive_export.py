"""
Google Drive exporter
- Auth via OAuth (installed app). First run opens a browser to grant access.
- Locate folder by a path-like string, e.g. "创业/Henry视频录屏"
- Download video files (.mp4/.mov/.mkv/.m4a/.mp3/.wav) into data/raw_videos/

Setup:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
Files:
  - Place credentials.json (OAuth client) in the project root
  - Token is saved to token.json after first auth

Usage:
  python -m src.ingest.gdrive_export --folder_path "创业/Henry视频录屏"
"""
import os, io, argparse, mimetypes
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MEDIA_EXTS = (".mp4",".mov",".mkv",".m4a",".mp3",".wav")

def get_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

def find_folder_id_by_path(service, folder_path: str) -> str:
    parts = [p for p in folder_path.strip("/").split("/") if p]
    parent = "root"
    for name in parts:
        q = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent}' in parents and trashed = false"
        res = service.files().list(q=q, fields="files(id,name)").execute()
        files = res.get("files", [])
        if not files:
            raise SystemExit(f"Folder not found at this level: {name}")
        parent = files[0]["id"]
    return parent

def list_files(service, folder_id: str):
    page_token = None
    while True:
        res = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        for f in res.get("files", []):
            yield f
        page_token = res.get("nextPageToken")
        if not page_token:
            break

def download_file(service, file_id: str, name: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(os.path.join(out_dir, name), "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        # print(f"Download {int(status.progress()*100)}%")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder_path", required=True, help='e.g. "创业/Henry视频录屏"')
    ap.add_argument("--out_dir", default="data/raw_videos")
    args = ap.parse_args()
    svc = get_service()
    folder_id = find_folder_id_by_path(svc, args.folder_path)
    print("Folder ID:", folder_id)
    for f in list_files(svc, folder_id):
        name = f["name"]
        if name.lower().endswith(MEDIA_EXTS):
            print("Downloading:", name)
            download_file(svc, f["id"], name, args.out_dir)
    print("Done.")

if __name__ == "__main__":
    main()
