import cv2
import numpy as np

def segment_image(frame):
    height, width = frame.shape
    labeled_image = np.zeros((height, width), dtype=np.int32)
    curr_label = 100
    for y in range(height):
        for x in range(width): 
            if frame[y,x] != 255 or labeled_image[y,x] != 0:
                continue
            if frame[y, x] == 255 and labeled_image[y,x] == 0:
                queue = [(x, y)]

                while queue:
                    cx, cy = queue.pop(0)
                    if labeled_image[cy, cx]:
                        continue
                    labeled_image[cy, cx] = curr_label
                    if (cx - 1 >= 0 and
                          labeled_image[cy, cx-1] == 0 and
                          frame[cy, cx-1] == 255):
                        queue.append((cx-1, cy))
                    if (cx + 1 < width and
                          labeled_image[cy, cx+1] == 0 and
                          frame[cy, cx+1] == 255):
                        queue.append((cx+1, cy))
                    if (cy + 1 < height and
                          labeled_image[cy + 1, cx] == 0 and
                          frame[cy+1, cx] == 255):
                        queue.append((cx, cy+1))
                    if (cy - 1 >= 0 and
                          labeled_image[cy - 1, cx] == 0 and
                          frame[cy-1, cx] == 255):
                        queue.append((cx, cy-1))
                curr_label += 1
    return labeled_image

def calc_centroids(segmented_image):
    unique_labels = np.unique(segmented_image)
    unique_labels = unique_labels[1:]

    centroids = []

    for label in unique_labels:
        y_coords, x_coords = np.where(segmented_image == label)
        x_centroid = np.mean(x_coords)
        y_centroid = np.mean(y_coords)
        n = len(x_coords)

        centroids.append((x_centroid, y_centroid, n))
    centroids.sort(key=lambda c: c[2], reverse=True)
    red_balls = centroids[:4]
    red_balls = np.array([[x, y] for x,y,size in red_balls])
    return red_balls
    
def main():
    cap = cv2.VideoCapture(1)

    if not cap.isOpened():
        exit()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_red1, upper_red1 = np.array([0, 100, 100]), np.array([10, 255, 255])
        lower_red2, upper_red2 = np.array([170, 100, 100]), np.array([180, 255, 255])
        red_mask = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)
        cv2.imshow("red_mask", red_mask)
        num_labels, labeled_image = cv2.connectedComponents(red_mask)

        centroids = []
        for label in range(1, num_labels):  # skip 0 (background)
            y_coords, x_coords = np.where(labeled_image == label)
            centroids.append((np.mean(x_coords), np.mean(y_coords), len(x_coords)))

        centroids.sort(key=lambda c: c[2], reverse=True)
        centroids = [c for c in centroids if c[2] > 500]
        centroids = centroids[:2]

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        balls = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            perimeter = cv2.arcLength(cnt, True)
            if area < 500 or perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity > 0.35:  # perfect circle = 1.0
                M = cv2.moments(cnt)
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                balls.append((cx, cy, area))
        for (cx, cy, area) in balls:
            radius = int(np.sqrt(area / np.pi))
            cv2.circle(frame, (cx, cy), radius, (0, 255, 0), 2)

        balls_detected = len(balls) >= 2
        if balls_detected:

            lower_blue = np.array([100, 100, 100])
            upper_blue = np.array([130, 255, 255])
            arrow_mask = cv2.inRange(hsv, lower_blue, upper_blue)

            h, w = arrow_mask.shape
            left_half = arrow_mask[:, :w//2]
            right_half = arrow_mask[:, w//2:]
            left_rows = np.any(left_half > 0, axis=1)
            right_rows = np.any(right_half > 0, axis=1)

            left_height = np.sum(left_rows)
            right_height = np.sum(right_rows)
            if right_height > left_height:
                cv2.putText(frame, "RIGHT", (w//2, 20), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 3)
            else:
                cv2.putText(frame, "LEFT", (w//2, 20), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 3)
        cv2.imshow("frame", frame)

        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
