import cv2
import numpy as np

def main():
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        exit()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]

        lower_blue = np.array([100, 100, 100])
        upper_blue = np.array([130, 255, 255])
        arrow_mask = cv2.inRange(hsv, lower_blue, upper_blue)

        cv2.imshow("arrow_mask", arrow_mask)

        left_half = arrow_mask[:, :w//2]
        right_half = arrow_mask[:, w//2:]

        left_height = np.sum(np.any(left_half > 0, axis=1))
        right_height = np.sum(np.any(right_half > 0, axis=1))

        total = left_height + right_height
        if total > 20:  # minimum threshold to avoid noise
            if right_height > left_height:
                cv2.putText(frame, "RIGHT", (w//2, 40), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 3)
            else:
                cv2.putText(frame, "LEFT", (w//2, 40), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 3)

        cv2.imshow("frame", frame)

        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()