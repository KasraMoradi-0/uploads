import cv2
import mediapipe as mp
import math
from tkinter import *
import tkinter as tk
import time
import subprocess
from PIL import ImageGrab
import os
import socket
import requests
import sys
from scapy.all import ARP, Ether, srp
import ipaddress
def main():
    # Initialize MediaPipe Hands
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.5)
    mp_drawing = mp.solutions.drawing_utils
    class ScreenCapture:
        """Create a fullscreen overlay for selecting a screen region."""
        def __init__(self):
            self.start_x = None
            self.start_y = None
            self.rect_id = None
            self.region = None

        def on_mouse_down(self, event):
            """Record the starting coordinates of the mouse."""
            self.start_x = event.x
            self.start_y = event.y

        def on_mouse_drag(self, event):
            """Draw a rectangle as the mouse is dragged."""
            if self.rect_id:
                self.canvas.delete(self.rect_id)
            self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="red", width=2)

        def on_mouse_release(self, event):
            """Capture the selected region."""
            end_x, end_y = event.x, event.y
            self.region = (self.start_x, self.start_y, end_x, end_y)
            self.root.quit()

        def capture_screen(self):
            """Launch the overlay and capture the region."""
            self.root = tk.Tk()
            self.root.attributes("-fullscreen", True)
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.3)  # Set window transparency
            self.root.configure(cursor="cross")  # Change cursor to crosshair
            self.canvas = tk.Canvas(self.root, bg="gray")  # Use gray as the background
            self.canvas.pack(fill=tk.BOTH, expand=True)
            self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
            self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
            self.root.mainloop()

            # Capture the selected region
            if self.region:
                x1, y1, x2, y2 = self.region
                screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
                return screen
            return None

    # DOESNT WORK FINE
    def save_and_share_image(image):
        """Save the image and update the Flask server's shared path."""
        global shared_image_path
        shared_image_path = "shared_image.png"
        image.save(shared_image_path)
        print(f"Image saved: {shared_image_path}")
        time.sleep(1)
        subprocess.Popen(["server.exe"])
        time.sleep(1)
        # Don't touch and don't replace with sys.exit(OR ANYTHING ELSE), it works fine don't ask me how
        os._exit(0)

    def get_local_ip_range():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
            return str(network)
        except Exception as e:
            print(f"Error calculating IP range: {e}")
            return None

    def scan_network(ip_range):
        arp_request = ARP(pdst=ip_range)
        broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
        arp_request_broadcast = broadcast / arp_request
        try:
            answered, _ = srp(arp_request_broadcast, timeout=2, verbose=False)
        except PermissionError:
            print("Permission denied: Run with elevated privileges.")
            return []

        devices = [{'IP': received.psrc, 'MAC': received.hwsrc} for _, received in answered]
        return devices
    # DOESNT WORK YET
    def find_server(devices):
        for device in devices:
            server_url = f"http://{device['IP']}:5000/shared_image.png"
            try:
                response = requests.head(server_url, timeout=2)
                if response.status_code == 200:
                    return server_url
            except requests.RequestException:
                continue
        return None

    def download_image(server_url):
        try:
            response = requests.get(server_url, timeout=5)
            if response.status_code == 200:
                file_path = "downloaded_image.jpg"
                with open(file_path, "wb") as file:
                    file.write(response.content)
                print(f"Image downloaded successfully: {file_path}")
                os.system("downloaded_image.jpg")
            else:
                print("Failed to download image.")
        except requests.RequestException as e:
            print(f"Error downloading image: {e}")
        main()
    # Initialize webcam
    cap = cv2.VideoCapture(0)
    previous_gesture = None
    detection_locked = False  # New state lock
    PROXIMITY_THRESHOLD = 150  # Adjust based on your needs

    def calculate_distance(landmark1, landmark2, frame_width, frame_height):
        x1, y1 = int(landmark1.x * frame_width), int(landmark1.y * frame_height)
        x2, y2 = int(landmark2.x * frame_width), int(landmark2.y * frame_height)
        return math.hypot(x2 - x1, y2 - y1)

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        current_gesture = None
        frame_height, frame_width, _ = frame.shape

        results = hands.process(rgb_frame)

        # Check detection lock state
        if detection_locked:
            if not results.multi_hand_landmarks:  # Hand removed
                detection_locked = False
            else:
                cv2.putText(frame, "Detection Locked", (20, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                continue

        if results.multi_hand_landmarks:
            for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                # Get handedness (front/back check)
                handedness = results.multi_handedness[hand_idx]
                label = handedness.classification[0].label

                # Get landmarks for orientation check
                thumb_tip = hand_landmarks.landmark[4]
                pinky_tip = hand_landmarks.landmark[20]

                # Skip back of hand detection
                if (label == 'Right' and thumb_tip.x >= pinky_tip.x) or \
                   (label == 'Left' and thumb_tip.x <= pinky_tip.x):
                    continue

                # Proximity check
                distance = calculate_distance(
                    hand_landmarks.landmark[0],
                    hand_landmarks.landmark[12],
                    frame_width,
                    frame_height
                )
                if distance < PROXIMITY_THRESHOLD:
                    continue

                # Gesture detection
                landmarks = hand_landmarks.landmark
                index_extended = landmarks[8].y < landmarks[7].y
                middle_extended = landmarks[12].y < landmarks[11].y
                ring_extended = landmarks[16].y < landmarks[15].y
                pinky_extended = landmarks[20].y < landmarks[19].y

                count = sum([index_extended, middle_extended, ring_extended, pinky_extended])
                gesture = "Open" if count >= 4 else "Closed"
                current_gesture = gesture

                # Display information
                wrist_x = int(landmarks[0].x * frame_width)
                wrist_y = int(landmarks[0].y * frame_height)
                cv2.putText(frame, gesture, (wrist_x - 50, wrist_y - 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        # Transition detection
        if current_gesture != previous_gesture and not detection_locked:
            if previous_gesture == "Open" and current_gesture == "Closed":
                screen_capture = ScreenCapture()
                selected_image = screen_capture.capture_screen()
                if selected_image:
                    save_and_share_image(selected_image)
                break
                detection_locked = True
            elif previous_gesture == "Closed" and current_gesture == "Open":
                ip_range = get_local_ip_range()
                if ip_range:
                    devices = scan_network(ip_range)
                    if devices:
                        server_url = find_server(devices)
                        if server_url:
                            print(f"Server found at {server_url}")
                            download_image(server_url)
                        else:
                            print("No server found.")
                    else:
                        print("No devices found on the network.")
                else:
                    print("Unable to determine the IP range.")
                break
                detection_locked = True

            previous_gesture = current_gesture
            
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
main()