from .health import router as health_router
from .upload import router as upload_router
from .delete import router as delete_router
from .query import router as query_router
from .files import router as files_router
from .groups import router as groups_router
from .chat import router as chat_router
from .storage import router as storage_router
from .gdrive import router as gdrive_router
from .addFromGoogleDrive import router as add_from_gdrive_router
from .onedrive import router as onedrive_router
from .addFromOneDrive import router as add_from_onedrive_router
from .tagging import router as tagging_router
from .user_settings import router as user_settings_router
from .stripe_payments import router as stripe_router
from .formatting import router as formatting_router
from .video import router as video_router

all_routers = [health_router, upload_router, delete_router, query_router, files_router, groups_router, chat_router, storage_router, gdrive_router, add_from_gdrive_router, onedrive_router, add_from_onedrive_router, tagging_router, user_settings_router, stripe_router, formatting_router, video_router]
