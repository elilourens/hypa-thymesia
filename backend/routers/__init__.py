from .health import router as health_router
from .upload import router as upload_router
from .delete import router as delete_router
from .query import router as query_router
from .files import router as files_router
from .groups import router as groups_router

all_routers = [health_router, upload_router, delete_router, query_router, files_router, groups_router]
