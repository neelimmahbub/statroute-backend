from supabase import create_client, Client
from app.config import get_settings

_settings = get_settings()

supabase: Client = create_client(_settings.supabase_url, _settings.supabase_key)
