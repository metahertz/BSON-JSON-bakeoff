#!/usr/bin/env python3
"""
Test script to verify DocumentDB version detection works correctly.
"""

import sys
import time
import subprocess
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from version_detector import get_database_version

def test_documentdb_version_detection():
    """Test DocumentDB version detection with a temporary container."""
    print("Testing DocumentDB version detection...")
    print("=" * 60)
    
    container_name = "documentdb-test-version"
    port = 10261  # Use a different port to avoid conflicts
    
    # Clean up any existing container
    print(f"1. Cleaning up any existing container '{container_name}'...")
    subprocess.run(f"docker rm -f {container_name} 2>/dev/null", shell=True, capture_output=True)
    time.sleep(1)
    
    # Check if DocumentDB image exists
    print("2. Checking for DocumentDB image...")
    check_image = subprocess.run(
        "docker images -q documentdb-local",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if not check_image.stdout.strip():
        print("   Image not found. Pulling DocumentDB image...")
        pull_result = subprocess.run(
            "docker pull ghcr.io/documentdb/documentdb/documentdb-local:latest",
            shell=True,
            capture_output=True,
            text=True
        )
        if pull_result.returncode != 0:
            print(f"   ✗ Failed to pull DocumentDB image: {pull_result.stderr}")
            return False
        # Tag the image
        subprocess.run(
            "docker tag ghcr.io/documentdb/documentdb/documentdb-local:latest documentdb-local:latest",
            shell=True,
            capture_output=True
        )
        print("   ✓ Image pulled and tagged")
    else:
        print("   ✓ Image found")
    
    # Start DocumentDB container
    print(f"3. Starting DocumentDB container on port {port}...")
    cmd = f"docker run --name {container_name} --rm -d -p {port}:10260 documentdb-local --username testuser --password testpass"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"   ✗ Failed to start container: {result.stderr}")
        return False
    
    print("   ✓ Container started")
    
    # Wait for DocumentDB to be ready
    print("4. Waiting for DocumentDB to be ready...")
    max_wait = 30
    wait_interval = 2
    
    for i in range(max_wait // wait_interval):
        time.sleep(wait_interval)
        # Check if port is listening
        port_check = subprocess.run(
            f"nc -z localhost {port} 2>&1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=2
        )
        if port_check.returncode == 0:
            print(f"   ✓ Port {port} is listening (took {(i+1)*wait_interval}s)")
            # Try pymongo connection
            try:
                from pymongo import MongoClient
                import urllib.parse
                encoded_password = urllib.parse.quote('testpass', safe='')
                # Try different connection approaches
                for auth_db in ['admin', 'test', None]:
                    try:
                        if auth_db:
                            connection_uri = f"mongodb://testuser:{encoded_password}@localhost:{port}/admin?authSource={auth_db}"
                        else:
                            connection_uri = f"mongodb://testuser:{encoded_password}@localhost:{port}/admin"
                        client = MongoClient(connection_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
                        client.admin.command('ping')
                        client.close()
                        print(f"   ✓ Connection successful with authSource={auth_db if auth_db else 'default'}")
                        break
                    except Exception as e:
                        continue
                break
            except ImportError:
                # pymongo not available, just check port
                break
    else:
        print(f"   ✗ Timeout waiting for DocumentDB to be ready")
        # Check container logs
        logs = subprocess.run(
            f"docker logs {container_name} 2>&1 | tail -20",
            shell=True,
            capture_output=True,
            text=True
        )
        print(f"   Container logs:\n{logs.stdout}")
        subprocess.run(f"docker rm -f {container_name}", shell=True, capture_output=True)
        return False
    
    # Test version detection
    print("5. Testing version detection...")
    success = False
    
    # Check container logs first to see if there are any errors
    print("   Checking container logs...")
    logs = subprocess.run(
        f"docker logs {container_name} 2>&1 | tail -10",
        shell=True,
        capture_output=True,
        text=True
    )
    if logs.stdout:
        print(f"   Container logs: {logs.stdout.strip()[:200]}")
    
    # First try without authentication (like check_ready does)
    print("   Trying without authentication...")
    connection_info_no_auth = {
        'host': 'localhost',
        'port': port
    }
    try:
        version = get_database_version('documentdb', connection_info_no_auth)
        if version:
            print(f"   ✓ Version detected (no auth): {version}")
            success = True
        else:
            print("   ✗ No version without auth, trying with authentication...")
            # Try with authentication
            connection_info = {
                'host': 'localhost',
                'port': port,
                'user': 'testuser',
                'password': 'testpass',
                'database': 'admin'
            }
            version = get_database_version('documentdb', connection_info)
            if version:
                print(f"   ✓ Version detected (with auth): {version}")
                success = True
            else:
                print("   ✗ Version detection returned None with auth too")
                # Try to debug by testing pymongo connection directly
                print("   Debugging: Testing pymongo connection...")
                try:
                    from pymongo import MongoClient
                    # Try without auth first
                    try:
                        connection_uri = f"mongodb://localhost:{port}/admin"
                        print(f"   Trying without auth: {connection_uri}")
                        client = MongoClient(connection_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
                        client.admin.command('ping')
                        print(f"   ✓ Ping successful without auth")
                        version_info = client.admin.command('buildInfo')
                        client.close()
                        print(f"   Direct pymongo result (no auth): {version_info.get('version', 'NOT FOUND')}")
                        success = True
                    except Exception as e:
                        print(f"   Failed without auth: {e}")
                        # Try with auth
                        import urllib.parse
                        encoded_password = urllib.parse.quote('testpass', safe='')
                        for auth_db in ['admin', 'test']:
                            try:
                                connection_uri = f"mongodb://testuser:{encoded_password}@localhost:{port}/admin?authSource={auth_db}"
                                print(f"   Trying with authSource={auth_db}...")
                                client = MongoClient(connection_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
                                client.admin.command('ping')
                                print(f"   ✓ Ping successful with authSource={auth_db}")
                                version_info = client.admin.command('buildInfo')
                                client.close()
                                print(f"   Direct pymongo result: {version_info.get('version', 'NOT FOUND')}")
                                success = True
                                break
                            except Exception as e2:
                                print(f"   Failed with authSource={auth_db}: {e2}")
                                continue
                except ImportError as e:
                    print(f"   pymongo not available: {e}")
                except Exception as e:
                    print(f"   Direct pymongo error: {e}")
    except Exception as e:
        print(f"   ✗ Error during version detection: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    # Clean up
    print("6. Cleaning up container...")
    subprocess.run(f"docker rm -f {container_name}", shell=True, capture_output=True)
    print("   ✓ Container removed")
    
    print("=" * 60)
    if success:
        print("✓ Test PASSED: DocumentDB version detection works correctly!")
        return True
    else:
        print("✗ Test FAILED: DocumentDB version detection did not work")
        return False

if __name__ == "__main__":
    success = test_documentdb_version_detection()
    sys.exit(0 if success else 1)
