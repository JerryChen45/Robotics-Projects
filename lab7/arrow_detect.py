import cv2
import numpy as np

LOWER_BGR = np.array([64, 19, 19])
UPPER_BGR = np.array([118, 150, 80])

def main():
    cap = cv2.VideoCapture("http://172.26.230.193:8080")

    if not cap.isOpened():
        print("Cannot connect to Pi stream")
        exit()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]

        arrow_mask = cv2.inRange(frame, LOWER_BGR, UPPER_BGR)

        cv2.imshow("arrow_mask", arrow_mask)

        left_half = arrow_mask[:, :w//2]
        right_half = arrow_mask[:, w//2:]

        left_height = np.sum(np.any(left_half > 0, axis=1))
        right_height = np.sum(np.any(right_half > 0, axis=1))

        total = left_height + right_height
        if total > 20:
            if right_height > left_height:
                direction = "RIGHT"
            else:
                direction = "LEFT"

            cv2.putText(frame, direction, (10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 3)

        cv2.imshow("frame", frame)

        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()