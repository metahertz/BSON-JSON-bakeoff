#!/usr/bin/env python3
"""
System information collection module.
Collects CPU, memory, OS, and hostname information.
"""

import os
import platform
import socket
import re
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def get_cpu_info() -> Dict[str, Any]:
    """
    Get CPU information from /proc/cpuinfo.
    
    Returns:
        Dictionary with CPU model, cores, and threads
    """
    cpu_info = {
        "model": "Unknown",
        "cores": 0,
        "threads": 0
    }
    
    try:
        cpuinfo_path = Path("/proc/cpuinfo")
        if cpuinfo_path.exists():
            with open(cpuinfo_path, 'r') as f:
                content = f.read()
            
            # Count physical cores (unique core IDs)
            core_ids = set()
            # Count logical processors (threads)
            processor_count = 0
            model_name = None
            
            for line in content.split('\n'):
                if line.startswith('processor'):
                    processor_count += 1
                elif line.startswith('model name'):
                    if model_name is None:
                        # Extract model name
                        model_name = line.split(':', 1)[1].strip()
                elif line.startswith('core id'):
                    core_id = line.split(':', 1)[1].strip()
                    if core_id:
                        core_ids.add(core_id)
            
            if model_name:
                cpu_info["model"] = model_name
            cpu_info["threads"] = processor_count
            # Physical cores = number of unique core IDs, or fallback to processor count
            cpu_info["cores"] = len(core_ids) if core_ids else processor_count
            
        else:
            # Fallback to platform module
            cpu_info["model"] = platform.processor()
            cpu_info["cores"] = os.cpu_count() or 0
            cpu_info["threads"] = os.cpu_count() or 0
            
    except Exception as e:
        logger.warning(f"Failed to get CPU info: {e}")
        # Fallback
        cpu_info["model"] = platform.processor() or "Unknown"
        cpu_info["cores"] = os.cpu_count() or 0
        cpu_info["threads"] = os.cpu_count() or 0
    
    return cpu_info


def get_memory_info() -> Dict[str, float]:
    """
    Get memory information from /proc/meminfo.
    
    Returns:
        Dictionary with total_gb and available_gb
    """
    memory_info = {
        "total_gb": 0.0,
        "available_gb": 0.0
    }
    
    try:
        meminfo_path = Path("/proc/meminfo")
        if meminfo_path.exists():
            with open(meminfo_path, 'r') as f:
                content = f.read()
            
            total_kb = None
            available_kb = None
            memfree_kb = None
            buffers_kb = None
            cached_kb = None
            
            for line in content.split('\n'):
                if line.startswith('MemTotal:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        total_kb = int(match.group(1))
                elif line.startswith('MemAvailable:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        available_kb = int(match.group(1))
                elif line.startswith('MemFree:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        memfree_kb = int(match.group(1))
                elif line.startswith('Buffers:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        buffers_kb = int(match.group(1))
                elif line.startswith('Cached:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        cached_kb = int(match.group(1))
            
            if total_kb:
                memory_info["total_gb"] = round(total_kb / (1024 * 1024), 2)
            
            if available_kb:
                memory_info["available_gb"] = round(available_kb / (1024 * 1024), 2)
            elif memfree_kb and buffers_kb and cached_kb:
                # Estimate available as free + buffers + cached
                available_kb = memfree_kb + buffers_kb + cached_kb
                memory_info["available_gb"] = round(available_kb / (1024 * 1024), 2)
            elif memfree_kb:
                memory_info["available_gb"] = round(memfree_kb / (1024 * 1024), 2)
                
    except Exception as e:
        logger.warning(f"Failed to get memory info: {e}")
    
    return memory_info


def get_os_info() -> Dict[str, str]:
    """
    Get OS information.
    
    Returns:
        Dictionary with OS name, version, and kernel
    """
    os_info = {
        "name": "Unknown",
        "version": "Unknown",
        "kernel": platform.release()
    }
    
    try:
        # Try /etc/os-release first (Linux)
        os_release_path = Path("/etc/os-release")
        if os_release_path.exists():
            with open(os_release_path, 'r') as f:
                content = f.read()
            
            for line in content.split('\n'):
                if line.startswith('NAME='):
                    name = line.split('=', 1)[1].strip().strip('"\'')
                    os_info["name"] = name
                elif line.startswith('VERSION='):
                    version = line.split('=', 1)[1].strip().strip('"\'')
                    os_info["version"] = version
        
        # Fallback to platform module
        if os_info["name"] == "Unknown":
            os_info["name"] = platform.system()
        if os_info["version"] == "Unknown":
            os_info["version"] = platform.version()
        
        # Kernel version
        os_info["kernel"] = platform.release()
        
    except Exception as e:
        logger.warning(f"Failed to get OS info: {e}")
        os_info["name"] = platform.system()
        os_info["version"] = platform.version()
        os_info["kernel"] = platform.release()
    
    return os_info


def get_hostname() -> str:
    """Get system hostname."""
    try:
        return socket.gethostname()
    except Exception as e:
        logger.warning(f"Failed to get hostname: {e}")
        return "unknown"


def get_system_info() -> Dict[str, Any]:
    """
    Get comprehensive system information.
    
    Returns:
        Dictionary with CPU, memory, OS, and hostname
    """
    return {
        "cpu": get_cpu_info(),
        "memory": get_memory_info(),
        "os": get_os_info(),
        "hostname": get_hostname()
    }


def get_ci_info() -> Dict[str, Any]:
    """
    Detect CI environment and collect CI metadata.
    
    Returns:
        Dictionary with CI information
    """
    ci_info = {
        "ci_run": False,
        "ci_platform": None,
        "commit_hash": None,
        "branch": None
    }
    
    # Check for generic CI flag
    if os.environ.get('CI') == 'true':
        ci_info["ci_run"] = True
    
    # GitHub Actions
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        ci_info["ci_run"] = True
        ci_info["ci_platform"] = "github"
        ci_info["commit_hash"] = os.environ.get('GITHUB_SHA')
        ci_info["branch"] = os.environ.get('GITHUB_REF_NAME') or os.environ.get('GITHUB_REF')
    
    # GitLab CI
    elif os.environ.get('GITLAB_CI') == 'true':
        ci_info["ci_run"] = True
        ci_info["ci_platform"] = "gitlab"
        ci_info["commit_hash"] = os.environ.get('CI_COMMIT_SHA')
        ci_info["branch"] = os.environ.get('CI_COMMIT_REF_NAME')
    
    # Jenkins
    elif os.environ.get('JENKINS_URL'):
        ci_info["ci_run"] = True
        ci_info["ci_platform"] = "jenkins"
        ci_info["commit_hash"] = os.environ.get('GIT_COMMIT')
        ci_info["branch"] = os.environ.get('GIT_BRANCH')
    
    # CircleCI
    elif os.environ.get('CIRCLECI') == 'true':
        ci_info["ci_run"] = True
        ci_info["ci_platform"] = "circleci"
        ci_info["commit_hash"] = os.environ.get('CIRCLE_SHA1')
        ci_info["branch"] = os.environ.get('CIRCLE_BRANCH')
    
    return ci_info
