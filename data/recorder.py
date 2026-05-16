"""
Client-Side Automatic Meeting Recorder (Time-Slice Chunking)
Records live audio and sends it to the API endpoint in chunks.
"""

import os
import time
import wave
import queue
import threading
import uuid
import sys
import requests
from pathlib import Path

try:
    import pyaudio
except ImportError:
    print("Please install pyaudio to use the meeting recorder:")
    print("pip install pyaudio")
    sys.exit(1)

# Audio configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

# Default configuration
DEFAULT_TIME_SLICE = 15 * 60  # 15 minutes per slice (900 seconds)
UPLOAD_URL = os.getenv("API_UPLOAD_URL", "http://localhost:8000/upload")

class MeetingRecorder:
    def __init__(self, meeting_id=None, time_slice_seconds=DEFAULT_TIME_SLICE, output_dir="data/local_records"):
        self.meeting_id = meeting_id or str(uuid.uuid4())
        self.time_slice = time_slice_seconds
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.p = pyaudio.PyAudio()
        self.is_recording = False
        self.q = queue.Queue()
        self.record_thread = None
        self.stream = None
        
    def start(self):
        """Start the live recording and chunking loop."""
        self.is_recording = True
        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=self._callback
        )
        
        self.record_thread = threading.Thread(target=self._recording_loop)
        self.record_thread.start()
        print(f"🎙️ Started recording meeting: {self.meeting_id}")
        print(f"⏱️ Time slice chunking set to: {self.time_slice} seconds")
        
    def stop(self):
        """Stop the recording gracefully and flush the last chunk."""
        print("\nStopping recording...")
        self.is_recording = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            
        self.p.terminate()
        
        if self.record_thread:
            self.record_thread.join()
            
        print("✅ Recording stopped.")
        
    def _callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback to put audio frames into the queue."""
        if self.is_recording:
            self.q.put(in_data)
        return (in_data, pyaudio.paContinue)
        
    def _recording_loop(self):
        """Main loop that collects frames and triggers saving when threshold is hit."""
        frames = []
        start_time = time.time()
        part_num = 1
        
        while self.is_recording or not self.q.empty():
            try:
                data = self.q.get(timeout=0.1)
                frames.append(data)
            except queue.Empty:
                continue
                
            current_time = time.time()
            if current_time - start_time >= self.time_slice:
                # Time threshold reached, dispatch chunk
                self._dispatch_chunk(frames.copy(), part_num)
                frames = []
                start_time = time.time()
                part_num += 1
                
        # Dispatch any remaining frames on stop
        if frames:
            self._dispatch_chunk(frames, part_num)
            
    def _dispatch_chunk(self, frames, part_num):
        """Save frames to file and spawn async upload task."""
        if not frames:
            return
            
        filename = self.output_dir / f"meeting_{self.meeting_id}_part_{part_num}.wav"
        
        # Write WAV file
        with wave.open(str(filename), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            
        print(f"\n📦 Chunk {part_num} saved to {filename}")
        
        # Fire and forget upload
        threading.Thread(target=self._upload_file, args=(str(filename), part_num)).start()
        
    def _upload_file(self, filename, part_num):
        """Upload the file to the FastAPI backend."""
        print(f"🚀 Uploading chunk {part_num}...")
        try:
            with open(filename, 'rb') as f:
                files = {'file': (os.path.basename(filename), f, 'audio/wav')}
                # Inject meeting_id as a custom header so the backend can group them later
                headers = {'X-Meeting-ID': self.meeting_id}
                response = requests.post(UPLOAD_URL, files=files, headers=headers)
                
            if response.status_code == 202:
                job_id = response.json().get('job_id')
                print(f"✅ Chunk {part_num} upload successful -> Job ID: {job_id}")
            else:
                print(f"❌ Upload failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error uploading {filename}: {e}")

if __name__ == "__main__":
    print("========================================")
    print(" Audio Intelligence - Time-Slice Recorder")
    print("========================================")
    
    
    demo_slice = 300  # 5 minutes for demo purposes 
    
    recorder = MeetingRecorder(time_slice_seconds=demo_slice)
    recorder.start()
    
    print("\nPress Ctrl+C to stop recording...\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        recorder.stop()
