import cv2
import torch
from ultralytics import YOLO
import os
import argparse
from pathlib import Path
import numpy as np
import colorsys
import subprocess
import time

def generate_distinct_colors(n):
    colors = []
    for i in range(n):
        hue = i / n
        rgb = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(hue, 0.8, 0.9))
        colors.append((rgb[2], rgb[1], rgb[0]))  # Convert to BGR for OpenCV
    return colors

def process_image(model, image_path, output_dir):
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Unable to read image {image_path}")
        return

    results = model(img)
    annotated_img = results[0].plot()

    output_filename = os.path.join(output_dir, f"result_{Path(image_path).name}")
    cv2.imwrite(output_filename, annotated_img)
    print(f"Processed image saved to: {output_filename}")

    cv2.imshow("Result", annotated_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

def process_video(model, video_path, output_dir):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Unable to open video {video_path}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    video_name = Path(video_path).stem
    temp_mp4_path = os.path.join(output_dir, f"temp_{video_name}.mp4")
    final_mov_path = os.path.join(output_dir, f"result_{video_name}.mov")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_mp4_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print(f"Error: Unable to create output video file")
        return

    frame_count = 0
    start_time = time.time()
    print(f"Processing video with {total_frames} frames...")

    cv2.namedWindow('Processing Video', cv2.WINDOW_NORMAL)

    screen_width = 1280
    screen_height = 720
    scale = min(screen_width / width, screen_height / height) * 0.8
    window_width = int(width * scale)
    window_height = int(height * scale)
    cv2.resizeWindow('Processing Video', window_width, window_height)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame)
        annotated_frame = results[0].plot()

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = model.names[cls_id]

                if label.lower() == 'traffic light':
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    tl_crop = frame[y1:y2, x1:x2]

                    if tl_crop.size == 0:
                        continue

                    hsv = cv2.cvtColor(tl_crop, cv2.COLOR_BGR2HSV)

                    lower_red1 = np.array([0, 70, 50])
                    upper_red1 = np.array([10, 255, 255])
                    lower_red2 = np.array([160, 70, 50])
                    upper_red2 = np.array([180, 255, 255])

                    lower_green = np.array([40, 70, 70])
                    upper_green = np.array([90, 255, 255])

                    lower_yellow = np.array([15, 70, 70])
                    upper_yellow = np.array([35, 255, 255])

                    mask_red = cv2.inRange(hsv, lower_red1, upper_red1) + cv2.inRange(hsv, lower_red2, upper_red2)
                    mask_green = cv2.inRange(hsv, lower_green, upper_green)
                    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

                    red_pixels = cv2.countNonZero(mask_red)
                    green_pixels = cv2.countNonZero(mask_green)
                    yellow_pixels = cv2.countNonZero(mask_yellow)

                    if red_pixels > green_pixels and red_pixels > yellow_pixels:
                        color_label = "Red"
                        color = (0, 0, 255)
                    elif green_pixels > red_pixels and green_pixels > yellow_pixels:
                        color_label = "Green"
                        color = (0, 255, 0)
                    elif yellow_pixels > red_pixels and yellow_pixels > green_pixels:
                        color_label = "Yellow"
                        color = (0, 255, 255)
                    else:
                        color_label = "Unknown"
                        color = (255, 255, 255)

                    cv2.putText(annotated_frame, f"{color_label} Light", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)

        out.write(annotated_frame)
        cv2.imshow('Processing Video', annotated_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break

        frame_count += 1
        elapsed = time.time() - start_time
        fps_processing = frame_count / elapsed if elapsed > 0 else 0

        if frame_count % 10 == 0:
            percent_done = (frame_count / total_frames) * 100 if total_frames > 0 else 0
            print(f"Progress: {frame_count}/{total_frames} frames ({percent_done:.1f}%) | Processing speed: {fps_processing:.1f} FPS", end="\r")

    cap.release()
    out.release()
    cv2.destroyAllWindows()

    print("\nVideo processing complete!")

    try:
        print("Converting to MOV format...")
        subprocess.run([
            "ffmpeg", "-i", temp_mp4_path, 
            "-c:v", "prores", "-profile:v", "3", 
            "-c:a", "pcm_s16le", final_mov_path,
            "-y"
        ], check=True)

        os.remove(temp_mp4_path)
        print(f"MOV video saved to: {final_mov_path}")

        try:
            import platform
            if platform.system() == "Darwin":
                subprocess.run(["open", final_mov_path])
            elif platform.system() == "Windows":
                os.startfile(final_mov_path)
            else:
                subprocess.run(["xdg-open", final_mov_path])
        except Exception as e:
            print(f"Unable to open video automatically: {str(e)}")

    except Exception as e:
        print(f"Failed to convert to MOV. MP4 file retained: {temp_mp4_path}")
        print(f"Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Process an image or video using a PyTorch model")
    parser.add_argument("--model", type=str, default="best.pt", help="Path to the model file")
    parser.add_argument("--source", type=str, required=True, help="Path to the image or video file")
    parser.add_argument("--output", type=str, default="output", help="Output directory")
    parser.add_argument("--exclude", type=str, default="", help="Comma-separated list of classes to exclude")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print(f"Loading model from {args.model}...")
    model = YOLO(args.model)

    source_path = args.source
    if source_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')):
        print(f"Processing image: {source_path}")
        process_image(model, source_path, args.output)
    elif source_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        print(f"Processing video: {source_path}")
        process_video(model, source_path, args.output)
    else:
        print("Unsupported file type. Please provide an image or video file.")

if __name__ == "__main__":
    main()