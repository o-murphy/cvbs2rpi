# USB camera display using PySide6 and OpenCV, based on sources from iosoft.blog
# Copyright (c) Jeremy P Bentham 2019
# Please credit iosoft.blog if you use the information or software in it
#
# Refactored to use PySide6 instead of PyQt
# Copyright (c) Dmytro Yaroshenko 2023


import queue
import sys
import threading
import time

import cv2
import imutils
from PySide6.QtCore import QTimer, QPoint, Signal, Qt, QRectF, QSize
from PySide6.QtGui import QFont, QPainter, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QGridLayout, QVBoxLayout, QGraphicsWidget, \
    QGraphicsView, QGraphicsScene, QGraphicsItem
from PySide6.QtWidgets import QWidget

__version__ = "0.0.1b0"

IMG_SIZE = 720, 540  # 640,480 or 1280,720 or 1920,1080
IMG_FORMAT = QImage.Format_RGB888
DISP_SCALE = 1  # Scaling factor for display image
DISP_MSEC = 16  # Delay between display cycles
CAP_API = cv2.CAP_ANY  # API: CAP_ANY or CAP_DSHOW etc...
EXPOSURE = 0  # Zero for automatic exposure
TEXT_FONT = QFont("Courier", 10)

camera_num = 1  # Default camera (first in list)
image_queue = queue.Queue()  # Queue to hold images
fps_queue = queue.Queue()  # Queue to hold images
capturing = True  # Flag to indicate capturing


# Grab images from the camera (separate thread)
def grab_images(cam_num: int, queue_: queue.Queue, fps_queue_: queue.Queue):
    cap = cv2.VideoCapture(cam_num - 1 + CAP_API)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, IMG_SIZE[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, IMG_SIZE[1])
    if EXPOSURE:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
        cap.set(cv2.CAP_PROP_EXPOSURE, EXPOSURE)
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
    while capturing:
        if cap.grab():
            retval, image = cap.retrieve(0)
            if image is not None and queue_.qsize() < 2:
                # resized = imutils.resize(image, width=IMG_SIZE[0] * 2)
                resized = imutils.resize(image, height=IMG_SIZE[1])
                queue_.put(resized)
            else:
                time.sleep(DISP_MSEC / 1000.0)
            fps = cap.get(cv2.CAP_PROP_FPS)  # TODO
            fps_queue_.put(fps)
            # print(fps)
        else:
            print("Error: can't grab camera image")
            break
    cap.release()


# Image widget
class ImageWidget(QWidget):
    def __init__(self, parent=None):
        super(ImageWidget, self).__init__(parent)
        self.image = None

    def setImage(self, image):
        self.image = image
        # self.setMinimumSize(image.size())

        self.setMinimumSize(self.parent().size())

        self.update()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        if self.image:
            qp.drawImage(QPoint(0, 0), self.image)
        qp.end()


class GraphicsCanvas(QGraphicsItem):
    def __init__(self, size: QSize, parent=None):
        super(GraphicsCanvas, self).__init__(parent)

        # self.pixmap = None
        # self.pixmap = QPixmap(size.width(), size.height())
        # self.pixmap.fill(Qt.transparent)
        
        
class Overlay(QGraphicsView):
    def __init__(self, parent=None):
        super(Overlay, self).__init__(parent)
        # self.layout_ = QVBoxLayout(self)
        # self.layout_.setAlignment(Qt.AlignTop)
        # self.label = QLabel()
        # self.label.setText("Sample")
        # self.label.setStyleSheet('color: "#00FF00"; font-style: bold; font-size: 32pt;')
        # self.layout_.addWidget(self.label)

        # self.label.move(1, 1)

        self.setStyleSheet("background: transparent")
        rect = QRectF(QPoint(0, 0), QPoint(self.size().width(), self.size().height()))
        self.scene_ = QGraphicsScene()
        self.scene_.setSceneRect(rect)
        self.setScene(self.scene_)

        self.fps = self.scene_.addText("0 FPS")

        self.scene_.addItem(self.fps)

    def display_fps(self, queue_: queue.Queue):
        if not queue_.empty():
            fps = queue_.get()
    #         self.label.setText(f"{fps} FPS")
            self.fps.setPlainText(f"{fps} FPS")



# Main window
class MyWindow(QMainWindow):
    text_update = Signal(str)

    # Create main window
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)

        self.setWindowFlags(Qt.FramelessWindowHint)
        # self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool | Qt.FramelessWindowHint)
        # self.setWindowFlags(Qt.CustomizeWindowHint | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        # self.setAttribute(Qt.WA_TranslucentBackground)
        # self.showFullScreen()
        self.showMaximized()

        screen = app.primaryScreen()
        size = screen.size()
        self.resize(size)

        self.central = QWidget(self)
        print("Camera number %u" % camera_num)
        print("Image size %u x %u" % IMG_SIZE)
        if DISP_SCALE > 1:
            print("Display scale %u:1" % DISP_SCALE)

        self.layout_ = QGridLayout(self)  # Window layout
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setAlignment(Qt.AlignRight)
        self.disp = ImageWidget(self)

        self.overlay = Overlay(self)

        self.layout_.addWidget(self.disp, 0, 0, alignment=Qt.AlignCenter)
        self.layout_.addWidget(self.overlay, 0, 0)

        self.central.setLayout(self.layout_)
        self.setCentralWidget(self.central)

    # Start image capture & display
    def start(self):
        self.timer = QTimer(self)  # Timer to trigger display
        self.timer.timeout.connect(lambda:
                                   self.show_image(image_queue, self.disp, DISP_SCALE))
        self.timer.timeout.connect(lambda:
                                   self.overlay.display_fps(fps_queue))
        self.timer.start(DISP_MSEC)
        self.capture_thread = threading.Thread(target=grab_images,
                                               args=(camera_num, image_queue, fps_queue))
        self.capture_thread.start()  # Thread to grab images

    # Fetch camera image from queue, and display it
    def show_image(self, imageq, display, scale):
        if not imageq.empty():
            image = imageq.get()
            if image is not None and len(image) > 0:
                img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                self.display_image(img, display, scale)

    # Display an image, reduce size if required
    def display_image(self, img, display, scale=1):
        disp_size = img.shape[1] // scale, img.shape[0] // scale
        disp_bpl = disp_size[0] * 3
        if scale > 1:
            img = cv2.resize(img, disp_size,
                             interpolation=cv2.INTER_CUBIC)
        qimg = QImage(img.data, disp_size[0], disp_size[1],
                      disp_bpl, IMG_FORMAT)
        display.setImage(qimg)

    def flush(self):
        pass

    # Window is closing: stop video capture
    def closeEvent(self, event):
        global capturing
        capturing = False
        self.capture_thread.join()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            camera_num = int(sys.argv[1])
        except:
            camera_num = 0
    if camera_num < 1:
        print("Invalid camera number '%s'" % sys.argv[1])
    else:
        app = QApplication(sys.argv)
        win = MyWindow()

        IMG_SIZE = win.size().width(), win.size().height()

        win.show()
        win.setWindowTitle(f"Cam display {__version__}")
        win.start()
        sys.exit(app.exec())
