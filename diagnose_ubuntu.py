#!/usr/bin/env python3
"""
Diagnostic script for RV Media Player on Ubuntu
Run this to identify issues with service initialization
"""

import os
import sys
import traceback
from pathlib import Path

def check_permissions(path, description):
    """Check if path exists and is accessible"""
    print(f"\n=== Checking {description} ===")
    print(f"Path: {path}")
    
    if os.path.exists(path):
        print(f"✓ Path exists")
        stat = os.stat(path)
        print(f"✓ Owner: {stat.st_uid}:{stat.st_gid}")
        print(f"✓ Permissions: {oct(stat.st_mode)[-3:]}")
        
        # Check read/write access
        if os.access(path, os.R_OK):
            print(f"✓ Readable")
        else:
            print(f"✗ Not readable")
            
        if os.access(path, os.W_OK):
            print(f"✓ Writable")
        else:
            print(f"✗ Not writable")
    else:
        print(f"✗ Path does not exist")
        
        # Try to create if it's a directory
        if path.endswith('/') or 'media' in path:
            try:
                os.makedirs(path, exist_ok=True)
                print(f"✓ Created directory")
            except Exception as e:
                print(f"✗ Cannot create directory: {e}")

def check_python_imports():
    """Check if all required Python modules can be imported"""
    print(f"\n=== Checking Python Imports ===")
    
    modules = [
        'flask',
        'requests', 
        'watchdog',
        'mutagen',
        'cryptography',
        'sqlite3',
        'json',
        'os',
        'sys'
    ]
    
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError as e:
            print(f"✗ {module}: {e}")

def check_vlc():
    """Check VLC installation"""
    print(f"\n=== Checking VLC ===")
    
    vlc_paths = ['/usr/bin/vlc', '/usr/local/bin/vlc', '/snap/bin/vlc']
    
    for path in vlc_paths:
        if os.path.exists(path):
            print(f"✓ VLC found at: {path}")
            if os.access(path, os.X_OK):
                print(f"✓ VLC is executable")
            else:
                print(f"✗ VLC is not executable")
            break
    else:
        print(f"✗ VLC not found in standard locations")

def test_service_initialization():
    """Test individual service initialization"""
    print(f"\n=== Testing Service Initialization ===")
    
    # Add app directory to Python path
    app_root = os.path.dirname(os.path.abspath(__file__))
    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    
    try:
        print("Testing configuration loading...")
        from config.configuration import Configuration
        config = Configuration.load_from_file()
        print(f"✓ Configuration loaded")
        print(f"  - Jellyfin URL: {config.jellyfin_server_url}")
        print(f"  - Media paths: {config.local_media_paths}")
        print(f"  - Download dir: {config.download_directory}")
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        traceback.print_exc()
        return
    
    try:
        print("\nTesting LocalMediaService...")
        from app.services.local_media_service import LocalMediaService
        
        # Use absolute path for database
        db_path = "/opt/rv-media-player/data/local_media.db" if os.path.exists('/opt/rv-media-player') else "media/local_media.db"
        
        # Ensure database directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        local_service = LocalMediaService(
            db_path=db_path,
            validation_cache_ttl=300,
            max_validation_workers=10
        )
        print(f"✓ LocalMediaService created")
        
        # Test media directory scanning
        print("Testing media directory scanning...")
        local_service.scan_media_directories(config.local_media_paths)
        print(f"✓ Media directory scan completed")
        
    except Exception as e:
        print(f"✗ LocalMediaService failed: {e}")
        traceback.print_exc()
        return
    
    try:
        print("\nTesting JellyfinService...")
        from app.services.jellyfin_service import JellyfinService
        
        jellyfin_service = JellyfinService(
            server_url=config.jellyfin_server_url,
            username=config.jellyfin_username,
            api_key=config.jellyfin_api_key
        )
        print(f"✓ JellyfinService created")
        
    except Exception as e:
        print(f"✗ JellyfinService failed: {e}")
        traceback.print_exc()
        return
    
    try:
        print("\nTesting VLCController...")
        from app.services.vlc_controller import VLCController
        
        vlc_controller = VLCController()
        print(f"✓ VLCController created")
        
    except Exception as e:
        print(f"✗ VLCController failed: {e}")
        traceback.print_exc()
        return
    
    try:
        print("\nTesting MediaManager...")
        from app.services.media_manager import MediaManager
        
        media_manager = MediaManager(
            local_service=local_service,
            jellyfin_service=jellyfin_service,
            vlc_controller=vlc_controller
        )
        print(f"✓ MediaManager created successfully!")
        
    except Exception as e:
        print(f"✗ MediaManager failed: {e}")
        traceback.print_exc()
        return

def main():
    print("RV Media Player Ubuntu Diagnostic Tool")
    print("=" * 50)
    
    print(f"Python version: {sys.version}")
    print(f"Current user: {os.getenv('USER', 'unknown')}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Check critical paths
    paths_to_check = [
        ("/media/movies", "Movies directory"),
        ("/media/tv-shows", "TV Shows directory"), 
        ("/media/downloads", "Downloads directory"),
        ("/opt/rv-media-player", "Application directory"),
        ("/opt/rv-media-player/data", "Data directory"),
        ("media/local_media.db", "Local database (relative)"),
        ("/opt/rv-media-player/data/local_media.db", "Local database (absolute)"),
    ]
    
    for path, desc in paths_to_check:
        check_permissions(path, desc)
    
    check_python_imports()
    check_vlc()
    test_service_initialization()
    
    print(f"\n=== Diagnostic Complete ===")

if __name__ == "__main__":
    main()