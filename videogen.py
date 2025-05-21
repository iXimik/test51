import os
import sys
import subprocess
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QPushButton, QLabel, QFileDialog, QLineEdit,
                            QMessageBox, QProgressBar)
from PyQt5.QtCore import QThread, pyqtSignal


class VideoCreatorThread(QThread):
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, images, output_path, fps, crf):
        super().__init__()
        self.images = images
        self.output_path = output_path
        self.fps = fps
        self.crf = crf

    def run(self):
        try:
            # Создаем временный файл со списком изображений
            list_file = os.path.join(os.path.dirname(self.output_path), "ffmpeg_list.txt")
            
            with open(list_file, 'w', encoding='utf-8') as f:
                for img in self.images:
                    f.write(f"file '{os.path.abspath(img)}'\nduration {1/float(self.fps)}\n")

            # Команда FFmpeg
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-r', str(self.fps),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', str(self.crf),
                '-preset', 'fast',
                '-y',  # Перезаписать без подтверждения
                os.path.abspath(self.output_path)
            ]

            # Запускаем процесс
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # Читаем вывод для прогресса
            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                if 'frame=' in line:
                    try:
                        frame = int(line.split('frame=')[1].split()[0])
                        progress = min(100, int((frame / len(self.images)) * 100))
                        self.progress_updated.emit(progress)
                    except:
                        pass

            # Проверяем результат
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)

            if not os.path.exists(self.output_path):
                raise Exception("Видеофайл не был создан")

            self.finished.emit(os.path.abspath(self.output_path))

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)


class VideoCreatorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Создание видео из изображений (рекурсивный поиск)")
        self.setGeometry(100, 100, 500, 400)
        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()

        # Элементы интерфейса
        self.folder_label = QLabel("Корневая папка с изображениями: не выбрана")
        self.select_folder_btn = QPushButton("Выбрать корневую папку")
        self.select_folder_btn.clicked.connect(self.select_folder)

        self.formats_label = QLabel("Поддерживаемые форматы: PNG, JPG, JPEG, BMP")
        
        self.output_label = QLabel("Сохранить видео в:")
        self.output_path_edit = QLineEdit()
        self.select_output_btn = QPushButton("Выбрать место сохранения")
        self.select_output_btn.clicked.connect(self.select_output)

        self.fps_label = QLabel("Частота кадров (FPS):")
        self.fps_input = QLineEdit("25")

        self.quality_label = QLabel("Качество (CRF 18-28):")
        self.quality_input = QLineEdit("23")

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("Готовность: 0%")

        self.create_btn = QPushButton("Создать видео")
        self.create_btn.clicked.connect(self.create_video)

        # Добавление элементов
        layout.addWidget(self.folder_label)
        layout.addWidget(self.select_folder_btn)
        layout.addWidget(self.formats_label)
        layout.addWidget(self.output_label)
        layout.addWidget(self.output_path_edit)
        layout.addWidget(self.select_output_btn)
        layout.addWidget(self.fps_label)
        layout.addWidget(self.fps_input)
        layout.addWidget(self.quality_label)
        layout.addWidget(self.quality_input)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.create_btn)

        central_widget.setLayout(layout)

        # Переменные
        self.selected_folder = ""
        self.output_path = ""
        self.worker_thread = None

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите корневую папку с изображениями")
        if folder:
            self.selected_folder = folder
            self.folder_label.setText(f"Корневая папка: {folder}")
            self.output_path_edit.setText(os.path.join(folder, "output.mp4"))

    def select_output(self):
        default_name = self.output_path_edit.text() or os.path.join(os.getcwd(), "output.mp4")
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить видео как", default_name, "MP4 Files (*.mp4)")
        if path:
            self.output_path = path
            self.output_path_edit.setText(path)

    def find_images_recursive(self, folder):
        """Рекурсивный поиск изображений во всех подпапках"""
        supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.PNG', '.JPG', '.JPEG', '.BMP')
        images = []
        
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(supported_formats):
                    images.append(os.path.join(root, file))
        
        return sorted(images)

    def create_video(self):
        if not self.selected_folder:
            QMessageBox.warning(self, "Ошибка", "Выберите корневую папку с изображениями")
            return

        self.output_path = self.output_path_edit.text()
        if not self.output_path:
            QMessageBox.warning(self, "Ошибка", "Укажите путь для сохранения видео")
            return

        try:
            fps = int(self.fps_input.text())
            crf = int(self.quality_input.text())
            if not (18 <= crf <= 28):
                raise ValueError("CRF должен быть между 18 и 28")
            if fps <= 0:
                raise ValueError("FPS должен быть положительным")
        except ValueError as e:
            QMessageBox.warning(self, "Ошибка", str(e))
            return

        # Рекурсивно ищем изображения
        images = self.find_images_recursive(self.selected_folder)

        if not images:
            QMessageBox.warning(self, "Ошибка", 
                              "Не найдены изображения в форматах: PNG, JPG, JPEG, BMP")
            return

        # Настраиваем UI
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"Найдено {len(images)} изображений. Готовность: 0%")
        self.create_btn.setEnabled(False)

        # Создаем и запускаем поток
        self.worker_thread = VideoCreatorThread(images, self.output_path, fps, crf)
        self.worker_thread.progress_updated.connect(self.update_progress)
        self.worker_thread.finished.connect(self.video_created)
        self.worker_thread.error_occurred.connect(self.show_error)
        self.worker_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        self.progress_label.setText(f"Готовность: {value}%")

    def video_created(self, output_path):
        self.progress_bar.setValue(100)
        self.progress_label.setText("Готовность: 100%")
        self.create_btn.setEnabled(True)
        
        file_size = os.path.getsize(output_path) / (1024 * 1024)  # в MB
        QMessageBox.information(
            self,
            "Готово",
            f"Видео успешно создано!\n\n"
            f"Путь: {output_path}\n"
            f"Размер: {file_size:.2f} MB\n"
            f"Кадров: {len(self.worker_thread.images)}\n"
            f"Длительность: {len(self.worker_thread.images) / int(self.fps_input.text()):.1f} сек")

    def show_error(self, error_msg):
        self.progress_bar.setValue(0)
        self.progress_label.setText("Ошибка!")
        self.create_btn.setEnabled(True)
        QMessageBox.critical(
            self,
            "Ошибка",
            f"Ошибка при создании видео:\n{error_msg[:500]}" +
            ("..." if len(error_msg) > 500 else ""))

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.terminate()
            self.worker_thread.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = VideoCreatorApp()
    window.show()
    sys.exit(app.exec_())
