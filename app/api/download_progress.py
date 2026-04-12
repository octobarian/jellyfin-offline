"""
Download Progress API endpoints for real-time progress tracking.
Provides Server-Sent Events for download progress updates.
"""

import json
import time
from flask import Blueprint, Response, request, jsonify
from typing import Dict, Any
import threading
import queue

download_progress_bp = Blueprint('download_progress', __name__)

# Global download tracking
active_downloads: Dict[str, Dict[str, Any]] = {}
progress_subscribers = []
progress_lock = threading.Lock()

class DownloadProgressTracker:
    """Manages download progress tracking and notifications."""
    
    def __init__(self):
        self.downloads = {}
        self.subscribers = []
    
    def start_download(self, task_id: str, media_id: str, media_info: dict):
        """Start tracking a new download."""
        with progress_lock:
            active_downloads[task_id] = {
                'media_id': media_id,
                'media_info': media_info,
                'progress': 0,
                'status': 'starting',
                'speed': 0,
                'eta': None,
                'start_time': time.time(),
                'error': None
            }
        
        self._notify_subscribers(task_id)
    
    def update_progress(self, task_id: str, progress: float, speed: float = None, eta: float = None):
        """Update download progress."""
        with progress_lock:
            if task_id in active_downloads:
                active_downloads[task_id].update({
                    'progress': progress,
                    'status': 'downloading',
                    'speed': speed,
                    'eta': eta
                })
                
                self._notify_subscribers(task_id)
    
    def complete_download(self, task_id: str):
        """Mark download as completed."""
        with progress_lock:
            if task_id in active_downloads:
                active_downloads[task_id].update({
                    'progress': 100,
                    'status': 'completed'
                })
                
                self._notify_subscribers(task_id)
                
                # Remove after a delay to allow UI to show completion
                threading.Timer(3.0, lambda: self._remove_download(task_id)).start()
    
    def fail_download(self, task_id: str, error: str = None):
        """Mark download as failed."""
        with progress_lock:
            if task_id in active_downloads:
                active_downloads[task_id].update({
                    'status': 'failed',
                    'error': error
                })
                
                self._notify_subscribers(task_id)
                
                # Remove after a delay
                threading.Timer(5.0, lambda: self._remove_download(task_id)).start()
    
    def cancel_download(self, task_id: str):
        """Cancel a download."""
        with progress_lock:
            if task_id in active_downloads:
                active_downloads[task_id].update({
                    'status': 'cancelled'
                })
                
                self._notify_subscribers(task_id)
                self._remove_download(task_id)
    
    def _remove_download(self, task_id: str):
        """Remove download from tracking."""
        with progress_lock:
            if task_id in active_downloads:
                del active_downloads[task_id]
    
    def _notify_subscribers(self, task_id: str):
        """Notify all subscribers of progress update."""
        if task_id in active_downloads:
            data = active_downloads[task_id].copy()
            data['task_id'] = task_id
            
            # Remove subscribers that are no longer connected
            active_subscribers = []
            for subscriber in progress_subscribers:
                try:
                    subscriber.put(data, timeout=0.1)
                    active_subscribers.append(subscriber)
                except queue.Full:
                    # Subscriber queue is full, remove it
                    pass
            
            progress_subscribers[:] = active_subscribers

# Global progress tracker instance
progress_tracker = DownloadProgressTracker()

@download_progress_bp.route('/api/download/progress')
def download_progress_stream():
    """Server-Sent Events endpoint for real-time download progress."""
    
    def event_stream():
        # Create a queue for this subscriber
        subscriber_queue = queue.Queue(maxsize=50)
        progress_subscribers.append(subscriber_queue)
        
        try:
            # Send current downloads on connection
            with progress_lock:
                for task_id, download_data in active_downloads.items():
                    data = download_data.copy()
                    data['task_id'] = task_id
                    yield f"data: {json.dumps(data)}\n\n"
            
            # Send periodic heartbeat and new updates
            while True:
                try:
                    # Wait for new data or timeout for heartbeat
                    data = subscriber_queue.get(timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    
        except GeneratorExit:
            # Client disconnected
            if subscriber_queue in progress_subscribers:
                progress_subscribers.remove(subscriber_queue)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )

@download_progress_bp.route('/api/download/cancel/<task_id>', methods=['POST'])
def cancel_download(task_id: str):
    """Cancel a download by task ID."""
    try:
        progress_tracker.cancel_download(task_id)
        
        # Here you would also cancel the actual download process
        # This depends on your download implementation
        
        return jsonify({'success': True, 'message': 'Download cancelled'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@download_progress_bp.route('/api/download/status')
def download_status():
    """Get current download status."""
    with progress_lock:
        return jsonify({
            'active_downloads': len(active_downloads),
            'downloads': {task_id: data for task_id, data in active_downloads.items()}
        })

# Export the progress tracker for use in other modules
__all__ = ['download_progress_bp', 'progress_tracker']
